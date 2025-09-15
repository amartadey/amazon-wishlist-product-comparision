import time
import csv
import re
import json
import signal
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

# --- Configuration ---
CONFIG_FILE = "wishlist_config.json"
OUTPUT_DIR = "scraped_data"
stop_requested = False
progress_lock = threading.Lock()

# --- Core Functions ---

def setup_driver():
    """Initializes and configures the Selenium WebDriver."""
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
    """Extracts a float price from a string."""
    if not text:
        return None
    match = re.search(r'₹\s*([\d,]+\.\d+|[\d,]+)', text)
    return float(match.group(1).replace(',', '')) if match else None

def get_book_details(driver, link, thread_id=0):
    """
    Fetches detailed information for a single book from its product page.
    """
    try:
        driver.get(link)
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.ID, "productTitle")))

        details = {
            "page_count": None, "review_count": None, "book_format": "Unknown",
            "has_keep_badge": False, "author": None, "publication_date": None,
            "asin": None, "avg_rating": None, "seller": None  # <-- ADDED: Initialize seller
        }

        # Extract ASIN from URL as a primary, reliable method
        asin_match = re.search(r'/dp/([A-Z0-9]{10})', link)
        if asin_match:
            details["asin"] = asin_match.group(1)

        # Extract details using robust, individual try-except blocks
        try:
            detail_text = driver.find_element(By.ID, "detailBullets_feature_div").text.lower()
            page_match = re.search(r'(\d+)\s*pages', detail_text)
            if page_match:
                details["page_count"] = int(page_match.group(1))
        except (NoSuchElementException, TimeoutException): pass

        try:
            review_text = driver.find_element(By.ID, "acrCustomerReviewText").text
            review_match = re.search(r'([\d,]+)', review_text)
            if review_match:
                details["review_count"] = int(review_match.group(1).replace(',', ''))
        except (NoSuchElementException, TimeoutException): pass

        try:
            rating_text = driver.find_element(By.CSS_SELECTOR, "span[data-hook='rating-out-of-text']").text
            rating_match = re.search(r'([\d\.]+)\s*out of 5', rating_text)
            if rating_match:
                details["avg_rating"] = float(rating_match.group(1))
        except (NoSuchElementException, TimeoutException): pass
        
        try:
            details["book_format"] = driver.find_element(By.CSS_SELECTOR, "#tmmSwatches .a-button-selected .a-button-text").text.strip()
        except (NoSuchElementException, TimeoutException): pass

        try:
            byline = driver.find_element(By.ID, "bylineInfo")
            authors = byline.find_elements(By.CSS_SELECTOR, ".author a")
            if authors:
                details["author"] = ", ".join([a.text for a in authors])
        except (NoSuchElementException, TimeoutException): pass

        # <-- ADDED: Section to extract the seller name -->
        try:
            # The most reliable element containing the seller's name has this ID.
            seller_element = driver.find_element(By.ID, "sellerProfileTriggerId")
            details["seller"] = seller_element.text.strip()
        except (NoSuchElementException, TimeoutException):
            # If the ID isn't found, leave the seller as None.
            pass

        return details

    except Exception as e:
        print(f"[Thread {thread_id}] Error extracting details for {link}: {e}")
        return None

def process_single_book(book_data, thread_id=0):
    """Orchestrates the processing of a single book."""
    if stop_requested: return None

    driver = setup_driver()
    try:
        link, title, price, initial_format, wishlist_name = book_data
        details = get_book_details(driver, link, thread_id)
        if not details: return None

        value_per_page = None
        if price and details.get("page_count") and details["page_count"] > 0:
            value_per_page = price / details["page_count"]

        # <-- MODIFIED: Added seller to the returned dictionary -->
        return {
            "title": title, "author": details.get("author"), "price": price,
            "pages": details.get("page_count"), "reviews": details.get("review_count"),
            "avg_rating": details.get("avg_rating"), "link": link, "asin": details.get("asin"),
            "seller": details.get("seller"), "value_per_page": value_per_page,
            "wishlist_name": wishlist_name, "format": details.get("book_format", initial_format),
            "scraped_timestamp": datetime.now().isoformat()
        }
    finally:
        driver.quit()

def scrape_wishlist_concurrent(wishlist_data, max_workers=4):
    """Scrapes a wishlist, handling scrolling, and processes books concurrently."""
    global stop_requested
    name, url = wishlist_data["name"], wishlist_data["url"]
    driver = setup_driver()
    books = []

    try:
        print(f"\n🚀 Processing Wishlist: {name}")
        driver.get(url)
        try:
            WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.ID, "sp-cc-accept"))).click()
        except (TimeoutException, NoSuchElementException): pass

        print("Scrolling to load all items...")
        last_height = driver.execute_script("return document.body.scrollHeight")
        while not stop_requested:
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            try:
                driver.find_element(By.CSS_SELECTOR, "span[data-action='show-more-items'] input").click()
                time.sleep(2)
            except (NoSuchElementException, TimeoutException): pass
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height: break
            last_height = new_height

        items = WebDriverWait(driver, 10).until(EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-itemid]")))
        print(f"Found {len(items)} items on the page.")

        book_data_list = []
        for item in items:
            try:
                title_elem = item.find_element(By.CSS_SELECTOR, "h2.a-size-base a.a-link-normal")
                title = title_elem.get_attribute("title").strip()
                link = title_elem.get_attribute("href").split("ref=")[0]
                price, initial_format = extract_book_price_and_format(item)
                book_data_list.append((link, title, price, initial_format, name))
            except (NoSuchElementException, StaleElementReferenceException): continue

        unique_books = {book[0]: book for book in book_data_list}
        book_data_list = list(unique_books.values())
        print(f"Processing {len(book_data_list)} unique books with {max_workers} workers...")

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_book = {executor.submit(process_single_book, book_data, i % max_workers): book_data for i, book_data in enumerate(book_data_list)}
            for i, future in enumerate(as_completed(future_to_book)):
                if stop_requested: break
                print_progress(i + 1, len(book_data_list), f"Scraping '{name}'")
                result = future.result()
                if result: books.append(result)
    finally:
        driver.quit()

    if books:
        save_results(books, name)
        print(f"\n✅ Saved {len(books)} books for '{name}'.")
    return books

# --- Helper & Utility Functions ---

def print_progress(iteration, total, prefix=''):
    if not total: return
    with progress_lock:
        percent = int(100 * (iteration / float(total)))
        bar = '█' * (percent // 2) + '-' * (50 - percent // 2)
        print(f'\r{prefix} |{bar}| {percent}% ({iteration}/{total})', end='\r')
        if iteration == total: print()

def handle_interrupt(signum, frame):
    global stop_requested
    if not stop_requested:
        stop_requested = True
        print("\n🛑 Stop requested. Finishing current tasks and saving results...")
        time.sleep(2)

def extract_book_price_and_format(item):
    price, item_format = None, "Unknown"
    try:
        price_text = item.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen").get_attribute("innerHTML")
        price = extract_price(price_text)
    except (NoSuchElementException, StaleElementReferenceException): pass
    try:
        item_format = item.find_element(By.ID, "item-platform").text.strip()
    except (NoSuchElementException, StaleElementReferenceException):
        item_text = item.text.lower()
        if "paperback" in item_text: item_format = "Paperback"
        elif "hardcover" in item_text: item_format = "Hardcover"
    return price, item_format

def save_results(books, wishlist_name):
    """Saves scraped data to JSON and CSV, updates historical data, and a combined file."""
    if not books: return

    # --- File Paths ---
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    wishlist_dir = os.path.join(OUTPUT_DIR, wishlist_name)
    os.makedirs(wishlist_dir, exist_ok=True)
    base_filename = os.path.join(wishlist_dir, f"{wishlist_name}_{timestamp}")
    
    # --- 1. Save Current Scrape for the individual wishlist ---
    save_to_json(books, f"{base_filename}.json")
    save_to_csv(books, f"{base_filename}.csv")

    # --- 2. Update Historical Data for the individual wishlist ---
    historical_path = os.path.join(wishlist_dir, "historical_data.json")
    all_time_data = []
    if os.path.exists(historical_path):
        with open(historical_path, "r", encoding="utf-8") as f:
            try:
                all_time_data = json.load(f)
            except json.JSONDecodeError:
                print(f"Warning: Could not read historical data for {wishlist_name}. Starting fresh.")
    
    all_time_data.extend(books)
    with open(historical_path, "w", encoding="utf-8") as f:
        json.dump(all_time_data, f, indent=4, ensure_ascii=False)
    
    print(f"Updated historical data for '{wishlist_name}'.")

    # --- 3. Update the Combined 'all_wishlists.json' File ---
    combined_json_path = os.path.join(OUTPUT_DIR, "all_wishlists.json")
    combined_books = []
    if os.path.exists(combined_json_path):
        with open(combined_json_path, "r", encoding="utf-8") as f:
            try:
                combined_books = json.load(f)
            except json.JSONDecodeError:
                print("Warning: Could not read combined wishlist file. A new one will be created.")

    # Create a dictionary of existing books by their unique link for efficient checking
    existing_links = {book['link']: book for book in combined_books}
    
    # Update existing entries and add new ones
    for book in books:
        existing_links[book['link']] = book # This will add new books or update existing ones

    # Convert the dictionary back to a list for saving
    updated_combined_list = list(existing_links.values())

    save_to_json(updated_combined_list, combined_json_path)
    print(f"✅ Updated combined 'all_wishlists.json' file with {len(updated_combined_list)} total unique items.")


def save_to_csv(books, filename):
    if not books: return
    # <-- MODIFIED: Added 'seller' to the list of CSV columns -->
    fields = [
        "title", "author", "price", "pages", "reviews", "avg_rating", 
        "seller", "value_per_page", "link", "asin", "wishlist_name", "format", 
        "scraped_timestamp"
    ]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction='ignore')
        writer.writeheader()
        writer.writerows(books)

def save_to_json(books, filename):
    with open(filename, "w", encoding="utf-8") as f:
        json.dump(books, f, indent=4, ensure_ascii=False)

def load_config():
    default_config = {
        "wishlists": [
            {"name": "Business Books", "url": "https://www.amazon.in/hz/wishlist/ls/1YZ6P9CMSTI9C?ref_=wl_share"},
            {"name": "General Books", "url": "https://www.amazon.in/hz/wishlist/ls/1VY69P3F07HC8?ref_=wl_share"},
            {"name": "IT Books", "url": "https://www.amazon.in/hz/wishlist/ls/OPIB1KQBJDHR?ref_=wl_share"},
            {"name": "Hardcover Books", "url": "https://www.amazon.in/hz/wishlist/ls/31VZFN51IPTZX?ref_=wl_share"},
            {"name": "Biography Books", "url": "https://www.amazon.in/hz/wishlist/ls/1YHK51DVJYR2A?ref_=wl_share"},
        ],
        "scraping": {"max_workers": 4}
    }
    if not os.path.exists(CONFIG_FILE):
        save_config(default_config)
        return default_config
    with open(CONFIG_FILE, "r", encoding='utf-8') as f:
        return json.load(f)

def save_config(config):
    with open(CONFIG_FILE, "w", encoding='utf-8') as f:
        json.dump(config, f, indent=4)

# --- Main Application & CLI ---

def analyze_data(wishlist_name):
    historical_file = os.path.join(OUTPUT_DIR, wishlist_name, "historical_data.json")
    if not os.path.exists(historical_file):
        print("No data found. Please scrape first.")
        return

    with open(historical_file, "r", encoding="utf-8") as f: data = json.load(f)
    latest_entries = {record['asin']: record for record in data if record.get('asin')}
    books = list(latest_entries.values())
    
    while True:
        print("\n--- Data Analysis ---")
        print("Sort by: 1. Price (Low to High)  2. Reviews (Most)  3. Value/Page (Best)  4. Back")
        choice = input("Choose an option: ")
        
        sorters = {
            '1': ('price', False), '2': ('reviews', True), '3': ('value_per_page', False)
        }
        if choice in sorters:
            key, reverse = sorters[choice]
            sorted_books = sorted([b for b in books if b.get(key) is not None], key=lambda x: x[key], reverse=reverse)
            print("\n--- Sorted Results (Top 15) ---")
            for book in sorted_books[:15]:
                price = f"₹{book['price']}" if book.get('price') else 'N/A'
                reviews = book.get('reviews', 'N/A')
                vpp = f"₹{book['value_per_page']:.2f}" if book.get('value_per_page') else 'N/A'
                # You can add seller to the printout here if you wish, e.g., | Seller: {book.get('seller', 'N/A')}
                print(f"- {book['title'][:50]:<50} | Price: {price:<10} | Reviews: {reviews:<10} | Value/Page: {vpp}")
            input("\nPress Enter to continue...")
        elif choice == '4': break
        else: print("Invalid choice.")

def main():
    signal.signal(signal.SIGINT, handle_interrupt)
    config = load_config()

    while True:
        print("\n" + "="*40 + "\n      Amazon Wishlist Scraper 2.0\n" + "="*40)
        print("1. Scrape All Wishlists\n2. Scrape a Single Wishlist\n3. Analyze Scraped Data\n4. Manage Wishlists (Edit Config)\n5. Exit")
        choice = input("Enter your choice (1-5): ")
        
        if choice == '1':
            for w_data in config["wishlists"]:
                if stop_requested: break
                scrape_wishlist_concurrent(w_data, config["scraping"]["max_workers"])
        elif choice == '2':
            for i, w in enumerate(config["wishlists"], 1): print(f"{i}. {w['name']}")
            try:
                idx = int(input("Select wishlist to scrape: ")) - 1
                if 0 <= idx < len(config["wishlists"]):
                    scrape_wishlist_concurrent(config["wishlists"][idx], config["scraping"]["max_workers"])
                else: print("Invalid selection.")
            except (ValueError, IndexError): print("Invalid selection.")
        elif choice == '3':
            for i, w in enumerate(config["wishlists"], 1): print(f"{i}. {w['name']}")
            try:
                idx = int(input("Select wishlist to analyze: ")) - 1
                if 0 <= idx < len(config["wishlists"]):
                    analyze_data(config["wishlists"][idx]['name'])
                else: print("Invalid selection.")
            except (ValueError, IndexError): print("Invalid selection.")
        elif choice == '4':
            print("To manage wishlists, please edit the 'wishlist_config.json' file directly.")
            input("Press Enter to continue...")
        elif choice == '5':
            print("Goodbye!"); break
        else:
            print("Invalid choice. Please try again.")

if __name__ == "__main__":
    main()