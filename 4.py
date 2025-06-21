import time
import csv
import re
import json
import signal
import os
import threading
import requests
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
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
IMAGES_DIR = "images"
stop_requested = False
progress_lock = threading.Lock()

def setup_driver():
    options = Options()
    options.add_argument("--headless")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = webdriver.Chrome(options=options)
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
    return driver

def extract_price(text):
    if not text:
        return None
    match = re.search(r'₹\s*([\d,]+\.\d+|[\d,]+)', text)
    return float(match.group(1).replace(',', '')) if match else None

def download_image(image_url, file_path):
    """Download image from URL and save to file_path"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        }
        response = requests.get(image_url, headers=headers, timeout=30)
        response.raise_for_status()
        
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'wb') as f:
            f.write(response.content)
        return True
    except Exception as e:
        print(f"Error downloading image {image_url}: {e}")
        return False

def get_product_image_url(driver):
    """Extract the main product image URL from the product page"""
    image_selectors = [
        "#landingImage",
        "#imgTagWrapperId img",
        ".a-dynamic-image",
        "#main-image",
        ".image.item img",
        "#ebooksImgBlkFront",
        "img[data-a-image-name='landingImage']"
    ]
    
    for selector in image_selectors:
        try:
            img_element = driver.find_element(By.CSS_SELECTOR, selector)
            # Try to get the highest resolution image
            image_url = (
                img_element.get_attribute("data-old-hires") or
                img_element.get_attribute("src") or
                img_element.get_attribute("data-src")
            )
            
            if image_url:
                # Clean up the URL and get the highest resolution version
                if "data-a-dynamic-image" in img_element.get_attribute("outerHTML"):
                    dynamic_images = img_element.get_attribute("data-a-dynamic-image")
                    if dynamic_images:
                        try:
                            images_dict = json.loads(dynamic_images.replace('&quot;', '"'))
                            # Get the image with highest resolution (largest dimensions)
                            max_area = 0
                            best_url = None
                            for url, dimensions in images_dict.items():
                                area = dimensions[0] * dimensions[1] if len(dimensions) >= 2 else 0
                                if area > max_area:
                                    max_area = area
                                    best_url = url
                            if best_url:
                                image_url = best_url
                        except:
                            pass
                
                return image_url
        except (NoSuchElementException, TimeoutException):
            continue
    
    return None

def generate_image_filename(title, image_url, wishlist_name):
    """Generate a safe filename for the image"""
    # Clean title for filename
    safe_title = re.sub(r'[^\w\s-]', '', title).strip()
    safe_title = re.sub(r'[-\s]+', '_', safe_title)[:50]  # Limit length
    
    # Get file extension from URL
    parsed_url = urlparse(image_url)
    file_ext = os.path.splitext(parsed_url.path)[1] or '.jpg'
    
    # Create filename
    timestamp = datetime.now().strftime("%Y%m%d")
    filename = f"{safe_title}_{timestamp}{file_ext}"
    
    return filename

def detect_book_format(driver):
    """Detect book format (paperback, hardcover, audiobook, etc.)"""
    format_selectors = [
        "#formats .a-button-selected .a-button-text",
        ".a-button-selected .a-button-text",
        "#tmmSwatches .a-button-selected .a-button-text",
        ".swatchElement.selected .a-button-text",
        "#mediaTab_heading_0",
        ".mediaTab_heading .a-color-base"
    ]
    
    for selector in format_selectors:
        try:
            element = driver.find_element(By.CSS_SELECTOR, selector)
            format_text = element.text.strip().lower()
            if format_text:
                # Clean up the format text
                if "paperback" in format_text:
                    return "Paperback"
                elif "hardcover" in format_text or "hardback" in format_text:
                    return "Hardcover"
                elif "kindle" in format_text or "ebook" in format_text:
                    return "Kindle/eBook"
                elif "audiobook" in format_text or "audible" in format_text:
                    return "Audiobook"
                elif "spiral" in format_text:
                    return "Spiral-bound"
                elif "board book" in format_text:
                    return "Board Book"
                else:
                    return format_text.title()
        except (NoSuchElementException, TimeoutException):
            continue
    
    # Try to find format in product title or description
    try:
        title = driver.find_element(By.ID, "productTitle").text.lower()
        if "paperback" in title:
            return "Paperback"
        elif "hardcover" in title or "hardback" in title:
            return "Hardcover"
        elif "kindle" in title:
            return "Kindle/eBook"
        elif "audiobook" in title or "audible" in title:
            return "Audiobook"
    except:
        pass
    
    return "Unknown"

def check_customer_keep_badge(driver):
    """Check if 'Customers usually keep this item' badge exists"""
    badge_selectors = [
        ".lcr-badge-T3",
        ".lcr-badge-suppress",
        "[class*='lcr-badge']"
    ]
    
    for selector in badge_selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
            for element in elements:
                text = element.text.lower()
                if "customers usually keep this item" in text or "fewer returns than average" in text:
                    return True
        except:
            continue
    
    # Alternative check - look for the specific text anywhere on the page
    try:
        page_text = driver.find_element(By.TAG_NAME, "body").text.lower()
        return "customers usually keep this item" in page_text
    except:
        pass
    
    return False

def get_book_details(driver, link, title, wishlist_name, thread_id=0):
    try:
        driver.get(link)
        time.sleep(2)
        
        # Consolidated page count extraction
        page_count = None
        for method in [
            lambda: re.search(r'(\d+)\s*pages', driver.find_element(By.ID, "detailBullets_feature_div").text.lower()),
            lambda: re.search(r'(\d+)', driver.find_element(By.ID, "productDetails_techSpec_section_1").text.lower()),
            lambda: re.search(r'(\d+)\s*pages', driver.find_element(By.ID, "productDescription").text.lower()),
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
            (By.CSS_SELECTOR, "span[data-hook='total-review-count']"),
            (By.CSS_SELECTOR, "[data-hook='total-review-count']")
        ]:
            try:
                text = driver.find_element(*selector).text
                match = re.search(r'([\d,]+)', text)
                if match:
                    review_count = int(match.group(1).replace(',', ''))
                    break
            except (NoSuchElementException, TimeoutException):
                continue

        # Detect book format
        book_format = detect_book_format(driver)
        
        # Check for customer keep badge
        has_keep_badge = check_customer_keep_badge(driver)
        
        # Get product image and download it
        image_url = get_product_image_url(driver)
        image_file_path = None
        
        if image_url:
            filename = generate_image_filename(title, image_url, wishlist_name)
            # Create wishlist-specific image directory
            wishlist_image_dir = os.path.join(OUTPUT_DIR, IMAGES_DIR, wishlist_name)
            image_file_path = os.path.join(wishlist_image_dir, filename)
            
            # Download the image
            if download_image(image_url, image_file_path):
                print(f"[Thread {thread_id}] Downloaded image: {filename}")
            else:
                image_file_path = None
                print(f"[Thread {thread_id}] Failed to download image for: {title}")

        return page_count, review_count, book_format, has_keep_badge, image_file_path
    except Exception as e:
        print(f"[Thread {thread_id}] Error extracting details for {link}: {e}")
        return None, None, "Unknown", False, None

def print_progress(iteration, total, prefix='', thread_id=0):
    if not total:
        return
    with progress_lock:
        percent = int(100 * iteration / total)
        bar = '█' * (percent // 2) + '-' * (50 - percent // 2)
        print(f'\r[Thread {thread_id}] {prefix} |{bar}| {percent}% ({iteration}/{total})', end='' if iteration < total else '\n')

def handle_interrupt(*args):
    global stop_requested
    if not stop_requested:
        stop_requested = True
        print("\nStopping... Saving results...")
        time.sleep(1)
        os._exit(0)

def extract_book_price_and_format(item):
    """Extract both price and format from wishlist item"""
    selectors = [
        ".a-price .a-offscreen", ".a-color-price", "span[data-a-color='price']",
        ".itemUsedAndNewPrice", ".a-price", "span[id*='price']"
    ]
    
    price = None
    item_format = "Unknown"
    
    # Extract price
    for selector in selectors:
        try:
            element = item.find_element(By.CSS_SELECTOR, selector)
            text = element.get_attribute("innerHTML") or element.text or element.get_attribute("value")
            price = extract_price(text)
            if price:
                break
        except (NoSuchElementException, StaleElementReferenceException):
            continue
    
    if not price:
        try:
            price = extract_price(item.text)
        except:
            pass
    
    # Try to extract format from item text
    try:
        item_text = item.text.lower()
        if "paperback" in item_text:
            item_format = "Paperback"
        elif "hardcover" in item_text or "hardback" in item_text:
            item_format = "Hardcover"
        elif "kindle" in item_text:
            item_format = "Kindle/eBook"
        elif "audiobook" in item_text or "audible" in item_text:
            item_format = "Audiobook"
    except:
        pass
    
    return price, item_format

def process_single_book(book_data, thread_id=0):
    """Process a single book with its own driver instance"""
    global stop_requested
    
    if stop_requested:
        return None
    
    driver = setup_driver()
    try:
        link, title, price, initial_format, wishlist_name = book_data
        pages, reviews, book_format, has_keep_badge, image_file_path = get_book_details(driver, link, title, wishlist_name, thread_id)
        
        # Use the more detailed format from the product page, fallback to initial format
        final_format = book_format if book_format != "Unknown" else initial_format
        
        value_per_page = price / pages if pages and price else None

        book = {
            "title": title,
            "price": price,
            "pages": pages,
            "reviews": reviews,
            "link": link,
            "value_per_page": value_per_page,
            "wishlist_name": wishlist_name,
            "format": final_format,
            "customers_keep_item": has_keep_badge,
            "image_file_path": image_file_path
        }
        return book
    except Exception as e:
        print(f"[Thread {thread_id}] Error processing book: {e}")
        return None
    finally:
        driver.quit()

def scrape_wishlist_concurrent(wishlist_data, max_workers=3):
    """Enhanced scraping with concurrent processing"""
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
        for _ in range(15):  # Increased scroll attempts
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

        book_data_list = []
        for item in items:
            if stop_requested:
                break
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, "h2 a, .a-link-normal > span")
                title = title_elem.text.strip() or title_elem.get_attribute("title") or title_elem.get_attribute("aria-label")
                link = title_elem.get_attribute("href") or item.find_element(By.XPATH, "./..").get_attribute("href")
                if "ref=" in link:
                    link = link.split("ref=")[0]
                if title and link:
                    price, initial_format = extract_book_price_and_format(item)
                    book_data_list.append((link, title, price, initial_format, name))
            except (NoSuchElementException, StaleElementReferenceException):
                continue

        # Remove duplicates based on link
        unique_books = {}
        for book_data in book_data_list:
            link = book_data[0]
            if link not in unique_books:
                unique_books[link] = book_data
        book_data_list = list(unique_books.values())

        print(f"Found {len(book_data_list)} unique books")
        
        # Process books concurrently
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_book = {
                executor.submit(process_single_book, book_data, i % max_workers): i 
                for i, book_data in enumerate(book_data_list)
            }
            
            completed = 0
            for future in as_completed(future_to_book):
                if stop_requested:
                    break
                
                completed += 1
                print_progress(completed, len(book_data_list), f"Processing {name}")
                
                try:
                    book = future.result()
                    if book:
                        books.append(book)
                        
                        # Save progress every 5 books
                        if len(books) % 5 == 0:
                            save_results(books, name)
                except Exception as e:
                    print(f"\nError processing book: {e}")

    finally:
        driver.quit()

    if books:
        save_results(books, name)
        print(f"\nSaved {len(books)} books for {name}")
    return books

def scrape_wishlist(wishlist_data):
    """Original sequential scraping method (kept for compatibility)"""
    return scrape_wishlist_concurrent(wishlist_data, max_workers=1)

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
    fields = ["title", "price", "pages", "reviews", "value_per_page", "link", "wishlist_name", "format", "customers_keep_item", "image_file_path"]
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
            {"name": "General Books", "url": "https://www.amazon.in/hz/wishlist/ls/1VY69P3F07HC8?ref_=wl_share"},
            {"name": "IT Books", "url": "https://www.amazon.in/hz/wishlist/ls/OPIB1KQBJDHR?ref_=wl_share"}
        ],
        "schedule": {"enabled": False, "time": "02:00", "frequency": "daily"},
        "scraping": {"max_workers": 3, "use_concurrent": True}
    }
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
                # Add new fields if they don't exist
                if "scraping" not in config:
                    config["scraping"] = default["scraping"]
                return config
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
    domains = ["amazon.com", "amazon.in", "amazon.co.uk", "amazon.ca", "amazon.de", "amazon.fr"]
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
                print("Wishlist added successfully!")
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
                        print("Wishlist updated successfully!")
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
                        print("Wishlist deleted successfully!")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Enter a number")
        elif choice == "5":
            break

def manage_scraping_settings(config):
    """Manage concurrent scraping settings"""
    scraping = config.get("scraping", {"max_workers": 3, "use_concurrent": True})
    while True:
        print(f"\nScraping Settings:")
        print(f"1. Concurrent Mode: {'Enabled' if scraping['use_concurrent'] else 'Disabled'}")
        print(f"2. Max Workers: {scraping['max_workers']}")
        print("3. Back")
        
        choice = input("Choice (1-3): ")
        if choice == "1":
            scraping["use_concurrent"] = not scraping["use_concurrent"]
            print(f"Concurrent mode {'enabled' if scraping['use_concurrent'] else 'disabled'}")
        elif choice == "2":
            try:
                workers = int(input(f"Max workers (1-8, current: {scraping['max_workers']}): "))
                if 1 <= workers <= 8:
                    scraping["max_workers"] = workers
                    print(f"Max workers set to {workers}")
                else:
                    print("Workers must be between 1 and 8")
            except ValueError:
                print("Enter a valid number")
        elif choice == "3":
            config["scraping"] = scraping
            save_config(config)
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
        print("\nAmazon Wishlist Scraper")
        print("=" * 40)
        print("1. Scrape All Wishlists")
        print("2. Scrape Single Wishlist")
        print("3. Manage Wishlists")
        print("4. Scraping Settings")
        print("5. Schedule Settings")
        print("6. Exit")
        
        choice = input("Choice (1-6): ")
        
        if choice == "1":
            all_books = []
            scraping_config = config.get("scraping", {"max_workers": 3, "use_concurrent": True})
            
            for w in config["wishlists"]:
                if scraping_config["use_concurrent"]:
                    books = scrape_wishlist_concurrent(w, scraping_config["max_workers"])
                else:
                    books = scrape_wishlist(w)
                all_books.extend(books)
                
            print(f"\nTotal scraped: {len(all_books)} books")
            
        elif choice == "2":
            for i, w in enumerate(config["wishlists"], 1):
                print(f"{i}. {w['name']}")
            try:
                idx = int(input("Select (number): ")) - 1
                if 0 <= idx < len(config["wishlists"]):
                    scraping_config = config.get("scraping", {"max_workers": 3, "use_concurrent": True})
                    
                    if scraping_config["use_concurrent"]:
                        books = scrape_wishlist_concurrent(config["wishlists"][idx], scraping_config["max_workers"])
                    else:
                        books = scrape_wishlist(config["wishlists"][idx])
                    print(f"Scraped {len(books)} books")
                else:
                    print("Invalid selection")
            except ValueError:
                print("Enter a number")
                
        elif choice == "3":
            manage_wishlists(config)
        elif choice == "4":
            manage_scraping_settings(config)
        elif choice == "5":
            manage_schedule(config)
        elif choice == "6":
            print("Goodbye!")
            break

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Unexpected error: {e}")
    except KeyboardInterrupt:
        print("\nExiting...")
        os._exit(0)