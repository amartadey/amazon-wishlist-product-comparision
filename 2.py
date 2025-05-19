import time
import csv
import re
import json
import signal
import os
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

CONFIG_FILE = "wishlist_config.json"
OUTPUT_DIR = "scraped_data"
stop_requested = False

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/96.0.4664.110 Safari/537.36")
    return webdriver.Chrome(options=options)

def extract_price(text):
    if not text:
        return None
    match = re.search(r'₹\s*([\d,]+\.\d+|[\d,]+)', text)
    return float(match.group(1).replace(',', '')) if match else None

def get_book_details(driver, link):
    try:
        driver.get(link)
        time.sleep(1)
        
        # Consolidated page count extraction
        page_count = None
        for method in [
            lambda: re.search(r'(\d+)\s*pages', driver.find_element(By.ID, "detailBullets_feature_div").text.lower()),
            lambda: re.search(r'(\d+)', driver.find_element(By.ID, "productDetails_techSpec_section_1").text.lower()),
            lambda: re.search(r'(\d+)\s*pages', driver.find_element(By.ID, "product productDescription").text.lower()),
            lambda: re.search(r'(\d+)\s*pages', ' '.join(t.text.lower() for t in driver.find_elements(By.TAG_NAME, "table")))
        ]:
            try:
                match = method()
                if match:
                    page_count = int(match.group(1))
                    break
            except (NoSuchElementException, TimeoutException):
                continue

        # Review count extraction
        review_count = None
        for selector in [
            (By.ID, "acrCustomerReviewText"),
            (By.CSS_SELECTOR, "span[data-hook='total-review-count']")
        ]:
            try:
                text = driver.find_element(*selector).text
                match = re.search(r'([\d,]+)', text)
                if match:
                    review_count = int(match.group(1).replace(',', ''))
                    break
            except (NoSuchElementException, TimeoutException):
                continue

        return page_count, review_count
    except Exception as e:
        print(f"Error extracting details for {link}: {e}")
        return None, None

def print_progress(iteration, total, prefix=''):
    if not total:
        return
    percent = int(100 * iteration / total)
    bar = '█' * (percent // 2) + '-' * (50 - percent // 2)
    print(f'\r{prefix} |{bar}| {percent}%', end='' if iteration < total else '\n')

def handle_interrupt(*args):
    global stop_requested
    if not stop_requested:
        stop_requested = True
        print("\nStopping... Saving results...")
        time.sleep(1)
        os._exit(0)

def extract_book_price(item):
    selectors = [
        ".a-price .a-offscreen", ".a-color-price", "span[data-a-color='price']",
        ".itemUsedAndNewPrice", ".a-price", "span[id*='price']"
    ]
    for selector in selectors:
        try:
            element = item.find_element(By.CSS_SELECTOR, selector)
            text = element.get_attribute("innerHTML") or element.text or element.get_attribute("value")
            price = extract_price(text)
            if price:
                return price
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    try:
        price = extract_price(item.text)
        if price:
            return price
    except:
        pass
    return None

def scrape_wishlist(wishlist_data):
    global stop_requested
    name, url = wishlist_data["name"], wishlist_data["url"]
    driver = setup_driver()
    books = []

    try:
        print(f"\nProcessing {name}: {url}")
        driver.get(url)
        time.sleep(2)

        # Accept cookies if present
        try:
            WebDriverWait(driver, 3).until(EC.element_to_be_clickable((By.ID, "sp-cc-accept"))).click()
        except (TimeoutException, NoSuchElementException):
            pass

        # Scroll to load items
        last_height = driver.execute_script("return document.body.scrollHeight")
        for _ in range(10):
            if stop_requested:
                break
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
            last_height = new_height

        # Find book items
        items = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-itemid], li.g-item-sortable"))
        )
        print(f"Found {len(items)} items")

        book_links, titles, prices = [], [], []
        for item in items:
            if stop_requested:
                break
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, "h2 a, .a-link-normal > span")
                title = title_elem.text.strip() or title_elem.get_attribute("title") or title_elem.get_attribute("aria-label")
                link = title_elem.get_attribute("href") or item.find_element(By.XPATH, "./..").get_attribute("href")
                if "ref=" in link:
                    link = link.split("ref=")[0]
                if title and link and link not in book_links:
                    price = extract_book_price(item)
                    book_links.append(link)
                    titles.append(title)
                    prices.append(price)
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        print(f"Found {len(book_links)} unique books")
        for i, link in enumerate(book_links):
            if stop_requested:
                break
            print_progress(i + 1, len(book_links), f"Processing {name}")
            try:
                title = titles[i]
                price = prices[i]
                pages, reviews = get_book_details(driver, link)
                value_per_page = price / pages if pages and price else None

                book = {
                    "title": title,
                    "price": price,
                    "pages": pages,
                    "reviews": reviews,
                    "link": link,
                    "value_per_page": value_per_page,
                    "wishlist_name": name
                }
                books.append(book)
                if (i + 1) % 5 == 0:
                    save_results(books, name)
            except Exception as e:
                print(f"\nError processing book {i+1}: {e}")
    finally:
        driver.quit()

    if books:
        save_results(books, name)
        print(f"Saved {len(books)} books for {name}")
    return books

def save_results(books, wishlist_name=None):
    timestamp = datetime.now().strftime("%Y%m%d")
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    if wishlist_name:
        wishlist_dir = os.path.join(OUTPUT_DIR, wishlist_name)
        os.makedirs(wishlist_dir, exist_ok=True)
        base = os.path.join(wishlist_dir, f"{wishlist_name}_{timestamp}")
        save_to_csv(books, f"{base}.csv")
        save_to_json(books, f"{base}.json")

    # Update combined file
    all_path = os.path.join(OUTPUT_DIR, "all_wishlists")
    all_json = f"{all_path}.json"
    existing_books = []
    if os.path.exists(all_json):
        with open(all_json, "r", encoding="utf-8") as f:
            existing_books = json.load(f)
    existing_links = {b["link"] for b in existing_books}
    new_books = [b for b in books if b["link"] not in existing_links]
    merged = existing_books + new_books

    with open(all_json, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=4, ensure_ascii=False)
    save_to_csv(merged, f"{all_path}.csv")
    print(f"Saved {len(merged)} books to combined file")

def save_to_csv(books, filename):
    fields = ["title", "price", "pages", "reviews", "value_per_page", "link", "wishlist_name"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(books)

def save_to_json(books, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=4, ensure_ascii=False)

def load_config():
    default = {
        "wishlists": [
            {"name": "Business Books", "url": "https://www.amazon.in/hz/wishlist/ls/1YZ6P9CMSTI9C?ref_=wl_share"},
            {"name": "IT Books", "url": "https://www.amazon.in/hz/wishlist/ls/OPIB1KQBJDHR?ref_=wl_share"}
        ],
        "schedule": {"enabled": False, "time": "02:00", "frequency": "daily"}
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(default, f, indent=4)
        return default
    except Exception as e:
        print(f"Error loading config: {e}")
        return default

def save_config(config):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=4)

def is_valid_amazon_wishlist_url(url):
    domains = ["amazon.com", "amazon.in", "amazon.co.uk", "amazon.ca"]
    return any(d in url.lower() for d in domains) and "wishlist" in url.lower()

def manage_wishlists(config):
    while True:
        print("\nWishlist Management: 1.View 2.Add 3.Edit 4.Delete 5.Back")
        choice = input("Choice (1-5): ")
        if choice == "1":
            for i, w in enumerate(config["wishlists"], 1):
                print(f"{i}. {w['name']} - {w['url']}")
        elif choice == "2":
            name = input("Name: ")
            url = input("URL: ")
            if is_valid_amazon_wishlist_url(url):
                config["wishlists"].append({"name": name, "url": url})
                save_config(config)
            else:
                print("Invalid URL")
        elif choice == "3":
            for i, w in enumerate(config["wishlists"], 1):
                print(f"{i}. {w['name']}")
            try:
                idx = int(input("Select (number): ")) - 1
                if 0 <= idx < len(config["wishlists"]):
                    w = config["wishlists"][idx]
                    new_name = input(f"New name (Enter to keep {w['name']}): ") or w["name"]
                    new_url = input(f"New URL (Enter to keep): ") or w["url"]
                    if new_url == w["url"] or is_valid_amazon_wishlist_url(new_url):
                        w["name"], w["url"] = new_name, new_url
                        save_config(config)
                    else:
                        print("Invalid URL")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Enter a number")
        elif choice == "4":
            for i, w in enumerate(config["wishlists"], 1):
                print(f"{i}. {w['name']}")
            try:
                idx = int(input("Select (number): ")) - 1
                if 0 <= idx < len(config["wishlists"]):
                    if input(f"Delete {config['wishlists'][idx]['name']}? (y/n): ").lower() == 'y':
                        config["wishlists"].pop(idx)
                        save_config(config)
                else:
                    print("Invalid selection")
            except ValueError:
                print("Enter a number")
        elif choice == "5":
            break

def manage_schedule(config):
    sched = config.get("schedule", {"enabled": False, "time": "02:00", "frequency": "daily"})
    while True:
        print(f"\nSchedule: 1.{'Enable' if not sched['enabled'] else 'Disable'} 2.Time ({sched['time']}) 3.Frequency ({sched['frequency']}) 4.Back")
        choice = input("Choice (1-4): ")
        if choice == "1":
            sched["enabled"] = not sched["enabled"]
        elif choice == "2":
            time = input("Time (HH:MM): ")
            if re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', time):
                sched["time"] = time
            else:
                print("Invalid format")
        elif choice == "3":
            freq = input("1.Daily 2.Weekly: ")
            sched["frequency"] = "daily" if freq == "1" else "weekly" if freq == "2" else sched["frequency"]
        elif choice == "4":
            config["schedule"] = sched
            save_config(config)
            break

def main():
    global stop_requested
    signal.signal(signal.SIGINT, handle_interrupt)
    config = load_config()

    while True:
        print("\nMenu: 1.Scrape All 2.Scrape One 3.Manage Wishlists 4.Schedule 5.Exit")
        choice = input("Choice (1-5): ")
        if choice == "1":
            all_books = []
            for w in config["wishlists"]:
                books = scrape_wishlist(w)
                all_books.extend(books)
            print(f"Scraped {len(all_books)} books")
        elif choice == "2":
            for i, w in enumerate(config["wishlists"], 1):
                print(f"{i}. {w['name']}")
            try:
                idx = int(input("Select (number): ")) - 1
                if 0 <= idx < len(config["wishlists"]):
                    books = scrape_wishlist(config["wishlists"][idx])
                    print(f"Scraped {len(books)} books")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Enter a number")
        elif choice == "3":
            manage_wishlists(config)
        elif choice == "4":
            manage_schedule(config)
        elif choice == "5":
            break

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Unexpected error: {e}")