import time
import csv
import re
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException

def setup_driver():
    """Set up and return a Chrome webdriver with appropriate options."""
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode (no browser UI)
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--window-size=1920x1080")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--disable-popup-blocking")
    
    # Add user agent to appear more like a regular browser
    chrome_options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/96.0.4664.110 Safari/537.36")
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def extract_price(price_text):
    """Extract the numeric price from the price text."""
    if not price_text:
        return None
    
    # Extract the price using regex
    price_match = re.search(r'₹\s*([\d,]+\.\d+|[\d,]+)', price_text)
    if price_match:
        # Remove commas and convert to float
        return float(price_match.group(1).replace(',', ''))
    return None

def get_book_details(driver, link):
    """Navigate to the book page and extract the page count and review count."""
    try:
        driver.get(link)
        time.sleep(3)  # Increased wait time for page to load
        
        page_count = None
        review_count = None
        
        # Look for page count in product details using multiple methods
        methods = [
            # Method 1: Detail bullets
            lambda: find_pages_in_detail_bullets(driver),
            # Method 2: Technical details table
            lambda: find_pages_in_tech_details(driver),
            # Method 3: Product description
            lambda: find_pages_in_description(driver),
            # Method 4: Table of book information
            lambda: find_pages_in_book_info(driver)
        ]
        
        # Try each method until we find a page count
        for method in methods:
            try:
                result = method()
                if result:
                    page_count = result
                    break
            except (NoSuchElementException, TimeoutException, StaleElementReferenceException):
                continue
        
        # Look for review count with multiple selectors
        review_selectors = [
            (By.ID, "acrCustomerReviewText"),
            (By.CSS_SELECTOR, "span[data-hook='total-review-count']"),
            (By.CSS_SELECTOR, "#averageCustomerReviews #acrCustomerReviewText")
        ]
        
        for selector_type, selector_value in review_selectors:
            try:
                review_element = WebDriverWait(driver, 3).until(
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
        print(f"Error extracting details for {link}: {e}")
        return None, None

def find_pages_in_detail_bullets(driver):
    """Find page count in the detail bullets section."""
    try:
        detail_bullets = WebDriverWait(driver, 5).until(
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
    """Find page count in the technical details table."""
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
    """Find page count in the product description."""
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
    """Find page count in any book information table."""
    try:
        # Look for any table with book information
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

def scrape_wishlist(wishlist_url):
    """Scrape the Amazon wishlist and return the book details."""
    driver = setup_driver()
    books = []
    
    try:
        driver.get(wishlist_url)
        time.sleep(5)  # Increased wait time for page to fully load
        
        # Accept cookies if the dialog appears
        try:
            cookie_button = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.ID, "sp-cc-accept"))
            )
            cookie_button.click()
            time.sleep(2)
        except (TimeoutException, NoSuchElementException):
            pass
        
        # Scroll down to trigger lazy loading of all books
        print("Scrolling to load all books...")
        scroll_to_load_all_items(driver)
        
        # Process books by getting their links first, then navigate to each one individually
        # This approach avoids stale element references
        book_links = []
        book_titles = []
        book_prices = []
        
        # Use WebDriverWait to ensure the page is fully loaded
        item_containers = WebDriverWait(driver, 15).until(
            EC.presence_of_all_elements_located((By.CSS_SELECTOR, "li[data-itemid]"))
        )
        
        print(f"Found {len(item_containers)} potential book items")
        
        # First, gather all the links, titles, and prices in one go
        for item in item_containers:
            try:
                # Get title and link directly from each item container to avoid stale references
                try:
                    title_element = item.find_element(By.CSS_SELECTOR, "h2 a")
                    book_title = title_element.text.strip()
                    book_link = title_element.get_attribute("href")
                    
                    if book_title and book_link and book_link not in book_links:
                        book_titles.append(book_title)
                        book_links.append(book_link)
                        
                        # Try to get the price near this title
                        try:
                            # Find the price element within this item container
                            price_element = item.find_element(By.CSS_SELECTOR, ".a-price .a-offscreen")
                            price_text = price_element.get_attribute("innerHTML")
                            price = extract_price(price_text)
                            book_prices.append(price)
                        except (NoSuchElementException, StaleElementReferenceException):
                            # If no price found, try alternate price selectors
                            try:
                                price_element = item.find_element(By.CSS_SELECTOR, ".a-color-price")
                                price_text = price_element.text
                                price = extract_price(price_text)
                                book_prices.append(price)
                            except (NoSuchElementException, StaleElementReferenceException):
                                book_prices.append(None)
                        
                        print(f"Found book: {book_title}, Link: {book_link}")
                except (NoSuchElementException, StaleElementReferenceException):
                    continue
            except Exception as e:
                print(f"Error finding book elements: {e}")
                continue
        
        print(f"Total unique books found: {len(book_links)}")
        
        # Now process each book individually
        for i, book_link in enumerate(book_links):
            try:
                book_title = book_titles[i] if i < len(book_titles) else f"Book {i+1}"
                price = book_prices[i] if i < len(book_prices) else None
                
                print(f"Processing book {i+1}/{len(book_links)}: {book_title}, Price: {price}")
                
                # Navigate to the book page to get additional details
                page_count, review_count = get_book_details(driver, book_link)
                
                # Calculate value per page
                value_per_page = None
                if page_count and price and price > 0:
                    value_per_page = page_count / price
                
                books.append({
                    "title": book_title,
                    "price": price,
                    "pages": page_count,
                    "reviews": review_count,
                    "link": book_link,
                    "value_per_page": value_per_page
                })
                
            except Exception as e:
                print(f"Error processing book {i+1}: {e}")
                continue
            
    except Exception as e:
        print(f"Error in scrape_wishlist: {e}")
    
    finally:
        driver.quit()
    
    return books

def scroll_to_load_all_items(driver, max_scroll_attempts=15, scroll_pause_time=2):
    """Scroll down repeatedly to trigger lazy loading of all items."""
    # Get initial height
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    # Counter for items found after each scroll
    last_item_count = 0
    no_change_count = 0
    
    try:
        for scroll_attempt in range(max_scroll_attempts):
            # Scroll down to bottom
            driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            
            # Wait to load page
            time.sleep(scroll_pause_time)
            
            # Count items currently visible
            items = driver.find_elements(By.CSS_SELECTOR, "li[data-itemid]")
            current_item_count = len(items)
            
            print(f"Scroll {scroll_attempt+1}/{max_scroll_attempts}: Found {current_item_count} items")
            
            # If no new items are loaded after several scrolls, we've probably reached the end
            if current_item_count == last_item_count:
                no_change_count += 1
                if no_change_count >= 3:  # Stop if no new items after 3 consecutive scrolls
                    print("No new items loaded after multiple scrolls. Assuming all items are loaded.")
                    break
            else:
                no_change_count = 0  # Reset counter if we found new items
                
            # Update item count for next comparison
            last_item_count = current_item_count
            
            # Calculate new scroll height and compare with last scroll height
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                # Try scrolling a bit less to trigger any remaining lazy loading
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.8);")
                time.sleep(scroll_pause_time)
                
                # Check if height changed after adjusted scroll
                newer_height = driver.execute_script("return document.body.scrollHeight")
                if newer_height == new_height:
                    # If still no change, we've probably reached the end
                    print("Reached end of page - no more scrolling needed")
                    break
                    
            last_height = new_height
    except Exception as e:
        print(f"Error while scrolling: {e}")

def save_to_csv(books, filename="amazon_books.csv"):
    """Save the book details to a CSV file."""
    fieldnames = ["title", "price", "pages", "reviews", "value_per_page", "link"]
    
    with open(filename, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for book in books:
            writer.writerow({
                "title": book["title"],
                "price": book["price"],
                "pages": book["pages"],
                "reviews": book["reviews"],
                "value_per_page": book["value_per_page"],
                "link": book["link"]
            })
    
    print(f"Data saved to {filename}")

def main():
    wishlist_url = "https://www.amazon.in/hz/wishlist/ls/1YZ6P9CMSTI9C?ref_=wl_share"
    print(f"Starting to scrape wishlist: {wishlist_url}")
    
    # Try multiple times if needed with a different approach each time
    max_attempts = 2
    books = []
    
    for attempt in range(1, max_attempts + 1):
        print(f"Attempt {attempt} of {max_attempts}...")
        books = scrape_wishlist(wishlist_url)
        
        if books and len(books) > 0:
            print(f"Successfully found {len(books)} books from the wishlist")
            break
        elif attempt < max_attempts:
            print("No books found or too few books, retrying with a different approach...")
            time.sleep(5)  # Wait before retrying
    
    if books:
        save_to_csv(books)
        print(f"Successfully scraped {len(books)} books from the wishlist")
        print(f"Data saved to amazon_books.csv")
    else:
        print("No books were found or there was an error scraping the wishlist")

if __name__ == "__main__":
    main()