import time
import csv
import re
import json
import signal
import sys
import os
import keyboard
import schedule
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

books_global = []
current_book = 0
total_books = 0
stop_requested = False
CONFIG_FILE = "wishlist_config.json"
DEFAULT_OUTPUT_DIR = "scraped_data"

def setup_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")  
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--log-level=3")
    chrome_options.add_argument("--silent")
    chrome_options.add_argument("--enable-unsafe-swiftshader")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def extract_price(price_text):
    if not price_text:
        return None
    
    price_match = re.search(r'₹\s*([\d,]+\.\d+|[\d,]+)', price_text)
    if price_match:
        return float(price_match.group(1).replace(',', ''))
    return None

def get_book_details(driver, link):
    try:
        print(f"Processing: {link.split('/')[-2] if '/' in link else link}")
        
        driver.get(link)
        time.sleep(2)
        
        page_count = None
        review_count = None
        
        methods = [
            lambda: find_pages_in_detail_bullets(driver),
            lambda: find_pages_in_tech_details(driver),
            lambda: find_pages_in_description(driver),
            lambda: find_pages_in_book_info(driver)
        ]
        
        for method in methods:
            try:
                result = method()
                if result:
                    page_count = result
                    break
            except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
                continue
        
        review_selectors = [
            (By.ID, "acrCustomerReviewText"),
            (By.CSS_SELECTOR, "span[data-hook='total-review-count']"),
            (By.CSS_SELECTOR, "#averageCustomerReviews #acrCustomerReviewText")
        ]
        
        for selector_type, selector_value in review_selectors:
            try:
                review_element = WebDriverWait(driver, 2).until(
                    EC.presence_of_element_located((selector_type, selector_value))
                )
                review_text = review_element.text
                review_match = re.search(r'([\d,]+)', review_text)
                if review_match:
                    review_count = int(review_match.group(1).replace(',', ''))
                    break
            except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
                continue
                
        return page_count, review_count
        
    except Exception as e:
        print(f"Error extracting details for {link}")
        return None, None

def find_pages_in_detail_bullets(driver):
    try:
        detail_bullets = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.ID, "detailBullets_feature_div"))
        )
        
        detail_items = detail_bullets.find_elements(By.CLASS_NAME, "a-list-item")
        for item in detail_items:
            text = item.text.lower()
            if "page" in text:
                page_match = re.search(r'(\d+)\s*pages', text)
                if page_match:
                    return int(page_match.group(1))
    except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
        pass
    return None

def find_pages_in_tech_details(driver):
    try:
        table_ids = ["productDetails_techSpec_section_1", "productDetails_detailBullets_sections1"]
        
        for table_id in table_ids:
            try:
                table = driver.find_element(By.ID, table_id)
                rows = table.find_elements(By.TAG_NAME, "tr")
                for row in rows:
                    text = row.text.lower()
                    if "page" in text:
                        page_match = re.search(r'(\d+)', text)
                        if page_match:
                            return int(page_match.group(1))
            except NoSuchElementException:
                continue
    except Exception:
        pass
    return None

def find_pages_in_description(driver):
    try:
        description = driver.find_element(By.ID, "productDescription")
        text = description.text.lower()
        page_match = re.search(r'(\d+)\s*pages', text)
        if page_match:
            return int(page_match.group(1))
    except (NoSuchElementException, StaleElementReferenceException):
        pass
    return None

def find_pages_in_book_info(driver):
    try:
        tables = driver.find_elements(By.TAG_NAME, "table")
        for table in tables:
            text = table.text.lower()
            if "page" in text:
                page_match = re.search(r'(\d+)\s*pages', text)
                if page_match:
                    return int(page_match.group(1))
    except (NoSuchElementException, StaleElementReferenceException):
        pass
    return None

def print_progress_bar(iteration, total, prefix='', suffix='', length=50, fill='█'):
    if total == 0:
        return
        
    percent = int(100 * (iteration / float(total)))
    filled_length = int(length * iteration // total)
    bar = fill * filled_length + '-' * (length - filled_length)
    
    print(f'\r{prefix} |{bar}| {percent}% {suffix}', end='\r')
    
    if iteration == total:
        print()

def handle_keyboard_interrupt(*args):
    global stop_requested, books_global
    
    if not stop_requested:
        print("\nStop requested. Saving current results...")
        stop_requested = True
        
        if books_global:
            save_results(books_global)
            print(f"Saved {len(books_global)} books to files. Terminating...")
        
        time.sleep(1)
        sys.exit(0)

def scrape_wishlist(wishlist_data):
    global books_global, current_book, total_books, stop_requested
    
    wishlist_url = wishlist_data["url"]
    wishlist_name = wishlist_data["name"]
    
    driver = setup_driver()
    books = []
    
    try:
        print(f"Loading wishlist: {wishlist_name} - {wishlist_url}")
        driver.get(wishlist_url)
        time.sleep(3)
        
        try:
            cookie_button = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.ID, "sp-cc-accept"))
            )
            cookie_button.click()
            time.sleep(1)
        except (TimeoutException, NoSuchElementException):
            pass
        
        print("Scrolling to load all books...")
        scroll_to_load_all_items(driver)
        
        book_links = []
        book_titles = []
        book_prices = []
        
        item_containers = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-itemid]"))
        )
        
        print(f"Found {len(item_containers)} potential book items")
        
        for item in item_containers:
            if stop_requested:
                break
                
            try:
                try:
                    title_element = item.find_element(By.CSS_SELECTOR, "h2 a")
                    book_title = title_element.text.strip()
                    book_link = title_element.get_attribute("href")
                    
                    if book_title and book_link and book_link not in book_links:
                        book_titles.append(book_title)
                        book_links.append(book_link)
                        
                        try:
                            price_element = item.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
                            price_text = price_element.get_attribute("innerHTML")
                            price = extract_price(price_text)
                            book_prices.append(price)
                        except (NoSuchElementException, StaleElementReferenceException):
                            try:
                                price_element = item.find_element(By.CSS_SELECTOR, ".a-color-price")
                                price_text = price_element.text
                                price = extract_price(price_text)
                                book_prices.append(price)
                            except (NoSuchElementException, StaleElementReferenceException):
                                book_prices.append(None)
                        
                        print(f"Found book: {book_title}")
                except (NoSuchElementException, StaleElementReferenceException):
                    continue
            except Exception as e:
                print(f"Error finding book elements")
                continue
        
        total_books = len(book_links)
        print(f"Total unique books found: {total_books}")
        
        for i, book_link in enumerate(book_links):
            if stop_requested:
                break
                
            current_book = i + 1
            
            print_progress_bar(current_book, total_books, 
                            prefix=f'Processing books: {current_book}/{total_books}',
                            suffix='Complete', length=50)
            
            try:
                book_title = book_titles[i] if i < len(book_titles) else f"Book {i+1}"
                price = book_prices[i] if i < len(book_prices) else None
                
                page_count, review_count = get_book_details(driver, book_link)
                
                value_per_page = None
                if page_count and price and price > 0:
                    value_per_page = price / page_count
                
                book_data = {
                    "title": book_title,
                    "price": price,
                    "pages": page_count,
                    "reviews": review_count,
                    "link": book_link,
                    "value_per_page": value_per_page,
                    "wishlist_name": wishlist_name
                }
                
                books.append(book_data)
                books_global = books.copy()
                
                if current_book % 5 == 0:
                    save_results(books, wishlist_name)
                    
            except Exception as e:
                print(f"\nError processing book {current_book}")
                continue
            
    except Exception as e:
        print(f"Error in scrape_wishlist: {e}")
    
    finally:
        driver.quit()
    
    return books

def scroll_to_load_all_items(driver, max_scroll_attempts=12, scroll_pause_time=1.5):
    global stop_requested
    
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    last_item_count = 0
    no_change_count = 0
    
    try:
        for scroll_attempt in range(max_scroll_attempts):
            if stop_requested:
                break
                
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            time.sleep(scroll_pause_time)
            
            items = driver.find_elements(By.CSS_SELECTOR, "li[data-itemid]")
            current_item_count = len(items)
            
            print(f"Scroll {scroll_attempt+1}/{max_scroll_attempts}: Found {current_item_count} items")
            
            if current_item_count == last_item_count:
                no_change_count += 1
                if no_change_count >= 3:
                    print("No new items loaded after multiple scrolls. Assuming all items are loaded.")
                    break
            else:
                no_change_count = 0
                
            last_item_count = current_item_count
            
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
                time.sleep(scroll_pause_time)
                
                newer_height = driver.execute_script("return document.body.scrollHeight")
                if newer_height == new_height:
                    print("Reached end of page - no more scrolling needed")
                    break
                    
            last_height = new_height
    except Exception as e:
        print(f"Error while scrolling")

def ensure_directory_exists(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)

def save_results(books, wishlist_name=None):
    timestamp = datetime.now().strftime("%Y%m%d")
    
    ensure_directory_exists(DEFAULT_OUTPUT_DIR)
    
    if wishlist_name:
        wishlist_dir = os.path.join(DEFAULT_OUTPUT_DIR, wishlist_name)
        ensure_directory_exists(wishlist_dir)
        base_filename = f"{wishlist_name}_{timestamp}"
        filepath = os.path.join(wishlist_dir, base_filename)
    else:
        base_filename = f"all_wishlists_{timestamp}"
        filepath = os.path.join(DEFAULT_OUTPUT_DIR, base_filename)
    
    save_to_csv(books, f"{filepath}.csv")
    save_to_json(books, f"{filepath}.json")

def save_to_csv(books, filename):
    fieldnames = ["title", "price", "pages", "reviews", "value_per_page", "link", "wishlist_name"]
    
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for book in books:
            writer.writerow(book)
    
    print(f"\nData saved to {filename}")

def save_to_json(books, filename):
    with open(filename, "w", encoding="utf-8") as jsonfile:
        json.dump(books, jsonfile, indent=4, ensure_ascii=False)
    
    print(f"Data saved to {filename}")

def load_config():
    default_config = {
        "wishlists": [
            {
                "name": "Business Books",
                "url": "https://www.amazon.in/hz/wishlist/ls/1YZ6P9CMSTI9C?ref_=wl_share"
            },
            {
                "name": "Papa",
                "url": "https://www.amazon.in/hz/wishlist/ls/2L0TRQKO0Y6SG?ref_=wl_share"
            }
        ],
        "schedule": {
            "enabled": False,
            "time": "02:00",
            "frequency": "daily"
        }
    }
    
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        else:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(default_config, f, indent=4)
            return default_config
    except Exception as e:
        print(f"Error loading config: {e}")
        return default_config

def save_config(config):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=4)
        print(f"Configuration saved to {CONFIG_FILE}")
    except Exception as e:
        print(f"Error saving config: {e}")

def is_valid_amazon_wishlist_url(url):
    amazon_domains = [
        "amazon.com", "amazon.in", "amazon.co.uk", "amazon.ca", "amazon.de", 
        "amazon.fr", "amazon.it", "amazon.es", "amazon.co.jp", "amazon.com.au"
    ]
    
    if not any(domain in url.lower() for domain in amazon_domains):
        return False
    
    wishlist_indicators = ["wishlist", "/hz/wishlist", "registry"]
    if not any(indicator in url.lower() for indicator in wishlist_indicators):
        return False
    
    return True

def manage_wishlists(config):
    while True:
        print("\n==== Wishlist Management ====")
        print("1. View all wishlists")
        print("2. Add a new wishlist")
        print("3. Edit a wishlist")
        print("4. Delete a wishlist")
        print("5. Return to main menu")
        
        choice = input("Enter your choice (1-5): ")
        
        if choice == "1":
            view_wishlists(config)
        elif choice == "2":
            add_wishlist(config)
        elif choice == "3":
            edit_wishlist(config)
        elif choice == "4":
            delete_wishlist(config)
        elif choice == "5":
            break
        else:
            print("Invalid choice. Please try again.")

def view_wishlists(config):
    wishlists = config.get("wishlists", [])
    
    if not wishlists:
        print("No wishlists found.")
        return
    
    print("\n==== Your Wishlists ====")
    for i, wishlist in enumerate(wishlists):
        print(f"{i+1}. {wishlist['name']} - {wishlist['url']}")

def add_wishlist(config):
    name = input("Enter wishlist name: ")
    url = input("Enter wishlist URL: ")
    
    while not is_valid_amazon_wishlist_url(url):
        print("Invalid Amazon wishlist URL. Please try again.")
        url = input("Enter wishlist URL: ")
    
    config["wishlists"].append({
        "name": name,
        "url": url
    })
    
    save_config(config)
    print(f"Wishlist '{name}' added successfully.")

def edit_wishlist(config):
    view_wishlists(config)
    
    if not config["wishlists"]:
        return
    
    try:
        index = int(input("\nEnter the number of the wishlist to edit: ")) - 1
        
        if 0 <= index < len(config["wishlists"]):
            wishlist = config["wishlists"][index]
            
            print(f"\nEditing: {wishlist['name']}")
            new_name = input(f"Enter new name (or press Enter to keep '{wishlist['name']}'): ")
            new_url = input(f"Enter new URL (or press Enter to keep '{wishlist['url']}'): ")
            
            if new_name:
                wishlist["name"] = new_name
            
            if new_url:
                while new_url and not is_valid_amazon_wishlist_url(new_url):
                    print("Invalid Amazon wishlist URL. Please try again.")
                    new_url = input(f"Enter new URL (or press Enter to keep '{wishlist['url']}'): ")
                
                if new_url:
                    wishlist["url"] = new_url
            
            save_config(config)
            print("Wishlist updated successfully.")
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input. Please enter a number.")

def delete_wishlist(config):
    view_wishlists(config)
    
    if not config["wishlists"]:
        return
    
    try:
        index = int(input("\nEnter the number of the wishlist to delete: ")) - 1
        
        if 0 <= index < len(config["wishlists"]):
            wishlist = config["wishlists"][index]
            
            confirm = input(f"Are you sure you want to delete '{wishlist['name']}'? (y/n): ")
            
            if confirm.lower() == 'y':
                del config["wishlists"][index]
                save_config(config)
                print("Wishlist deleted successfully.")
        else:
            print("Invalid selection.")
    except ValueError:
        print("Invalid input. Please enter a number.")

def manage_schedule(config):
    schedule_config = config.get("schedule", {
        "enabled": False,
        "time": "02:00",
        "frequency": "daily"
    })
    
    while True:
        print("\n==== Schedule Configuration ====")
        print(f"1. Scheduling: {'Enabled' if schedule_config.get('enabled', False) else 'Disabled'}")
        print(f"2. Time: {schedule_config.get('time', '02:00')}")
        print(f"3. Frequency: {schedule_config.get('frequency', 'daily')}")
        print("4. Return to main menu")
        
        choice = input("Enter your choice (1-4): ")
        
        if choice == "1":
            schedule_config["enabled"] = not schedule_config.get("enabled", False)
            print(f"Scheduling {'enabled' if schedule_config['enabled'] else 'disabled'}.")
        elif choice == "2":
            new_time = input("Enter time in 24-hour format (HH:MM): ")
            
            if re.match(r'^([01]\d|2[0-3]):([0-5]\d)$', new_time):
                schedule_config["time"] = new_time
                print(f"Time set to {new_time}")
            else:
                print("Invalid time format. Please use HH:MM in 24-hour format.")
        elif choice == "3":
            print("\nAvailable frequencies:")
            print("1. daily")
            print("2. weekly")
            freq_choice = input("Choose frequency (1-2): ")
            
            if freq_choice == "1":
                schedule_config["frequency"] = "daily"
            elif freq_choice == "2":
                schedule_config["frequency"] = "weekly"
            else:
                print("Invalid choice. Setting to daily.")
                schedule_config["frequency"] = "daily"
                
            print(f"Frequency set to {schedule_config['frequency']}")
        elif choice == "4":
            config["schedule"] = schedule_config
            save_config(config)
            break
        else:
            print("Invalid choice. Please try again.")

def run_scheduled_task():
    print("\n" + "=" * 70)
    print(f"Running scheduled scrape at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 70)
    
    config = load_config()
    all_books = []
    
    for wishlist in config["wishlists"]:
        try:
            print(f"\nProcessing wishlist: {wishlist['name']}")
            books = scrape_wishlist(wishlist)
            all_books.extend(books)
            
            if books:
                save_results(books, wishlist["name"])
                print(f"Saved {len(books)} books for wishlist '{wishlist['name']}'")
        except Exception as e:
            print(f"Error processing wishlist '{wishlist['name']}': {e}")
    
    if all_books:
        save_results(all_books)
        print(f"Total books scraped: {len(all_books)}")
    else:
        print("No books were scraped.")

def run_scheduler():
    config = load_config()
    schedule_config = config.get("schedule", {})
    
    if not schedule_config.get("enabled", False):
        print("Scheduling is disabled.")
        return
    
    scheduled_time = schedule_config.get("time", "02:00")
    frequency = schedule_config.get("frequency", "daily")
    
    print(f"Scheduler set to run {frequency} at {scheduled_time}")
    
    if frequency == "daily":
        schedule.every().day.at(scheduled_time).do(run_scheduled_task)
    elif frequency == "weekly":
        schedule.every().monday.at(scheduled_time).do(run_scheduled_task)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute
    except KeyboardInterrupt:
        print("\nScheduler stopped.")

def main():
    global stop_requested
    
    keyboard.add_hotkey('ctrl+c', handle_keyboard_interrupt)
    signal.signal(signal.SIGINT, handle_keyboard_interrupt)
    
    config = load_config()
    
    print("=" * 70)
    print("          Enhanced Amazon Wishlist Book Scraper")
    print("=" * 70)
    print("Press 'Ctrl+C' at any time to stop and save current results.")
    print("=" * 70)
    
    while True:
        print("\n==== Main Menu ====")
        print("1. Scrape all wishlists")
        print("2. Scrape a specific wishlist")
        print("3. Manage wishlists")
        print("4. Configure scheduler")
        print("5. Run scheduler")
        print("6. Exit")
        
        choice = input("Enter your choice (1-6): ")
        
        if choice == "1":
            all_books = []
            
            for wishlist in config["wishlists"]:
                try:
                    print(f"\nProcessing wishlist: {wishlist['name']}")
                    books = scrape_wishlist(wishlist)
                    all_books.extend(books)
                    
                    if books:
                        save_results(books, wishlist["name"])
                except Exception as e:
                    print(f"Error processing wishlist '{wishlist['name']}': {e}")
            
            if all_books:
                save_results(all_books)
                print(f"Total books scraped: {len(all_books)}")
            else:
                print("No books were scraped.")
                
        elif choice == "2":
            view_wishlists(config)
            
            if not config["wishlists"]:
                continue
                
            try:
                index = int(input("\nEnter the number of the wishlist to scrape: ")) - 1
                
                if 0 <= index < len(config["wishlists"]):
                    wishlist = config["wishlists"][index]
                    books = scrape_wishlist(wishlist)
                    
                    if books:
                        save_results(books, wishlist["name"])
                        print(f"Successfully scraped {len(books)} books from '{wishlist['name']}'")
                    else:
                        print("No books were found in this wishlist.")
                else:
                    print("Invalid selection.")
            except ValueError:
                print("Invalid input. Please enter a number.")
                
        elif choice == "3":
            manage_wishlists(config)
            config = load_config()  # Reload config after changes
            
        elif choice == "4":
            manage_schedule(config)
            config = load_config()  # Reload config after changes
            
        elif choice == "5":
            print("Running scheduler in background. Press Ctrl+C to stop.")
            run_scheduler()
            
        elif choice == "6":
            print("Thank you for using the Amazon Wishlist Book Scraper. Goodbye!")
            break
            
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        handle_keyboard_interrupt()
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        if books_global:
            print(f"Saving {len(books_global)} books that were scraped before the error...")
            save_results(books_global)