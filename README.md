pip install requests beautifulsoup4

pip install selenium


# Amazon Wishlist Scraper

A powerful Python tool for scraping and analyzing books from Amazon wishlists with advanced features like real-time progress tracking, emergency saving, and data export functionality.

## Features

- **Automated Web Scraping**: Extract book details from any Amazon wishlist URL
- **Data Collection**: Collects title, price, page count, review count, and value metrics for each book
- **Real-time Progress Display**: GUI progress bar shows current status and completion percentage
- **Multiple Export Formats**: Automatically saves data in both CSV and JSON formats
- **Emergency Save**: Press `Ctrl+C` at any time to save current progress and exit gracefully
- **Robust Error Handling**: Automatically recovers from common website structure changes
- **Periodic Autosaving**: Saves progress every 5 books to prevent data loss
- **Input Validation**: Verifies wishlist URLs before attempting to scrape

## Installation

Clone this repository and install the required dependencies:

```bash
# Clone the repository
git clone https://github.com/yourusername/amazon-wishlist-scraper.git
cd amazon-wishlist-scraper

# Create a virtual environment (optional but recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install required packages
pip install selenium
pip install keyboard
pip install schedule
```

## Additional Requirements

1. **ChromeDriver**: The script uses Chrome in headless mode. Make sure you have Chrome installed.

2. **Selenium WebDriver**: The script will automatically use the appropriate WebDriver.

## Usage

1. Run the script:

```bash
python wishlist_scraper.py
```

2. If no default wishlist URL is specified in the code, you'll be prompted to enter one.

3. The scraper will:
   - Launch a GUI progress window
   - Start collecting book data
   - Display real-time progress
   - Save data periodically and at completion

## Keyboard Shortcuts

| Shortcut | Action |
|----------|--------|
| `Ctrl+C` | Stop scraping and save all data collected so far |

You can press `Ctrl+C` at any time to gracefully terminate the program. The script will:
1. Stop all current operations
2. Save all data collected up to that point in both CSV and JSON formats
3. Show a completion message
4. Close gracefully

## Output Files

After running the script, you'll find two files in the script's directory:

- **amazon_books.csv**: Comma-separated values file for easy import into Excel or Google Sheets
- **amazon_books.json**: JSON-formatted data for programmatic access

## Example Output Structure

### CSV Format:
```
title,price,pages,reviews,value_per_page,link
"Book Title 1",499.0,320,42,0.64,"https://www.amazon.in/dp/..."
"Book Title 2",299.0,180,15,0.60,"https://www.amazon.in/dp/..."
```

### JSON Format:
```json
[
    {
        "title": "Book Title 1",
        "price": 499.0,
        "pages": 320,
        "reviews": 42,
        "value_per_page": 0.64,
        "link": "https://www.amazon.in/dp/..."
    },
    {
        "title": "Book Title 2",
        "price": 299.0,
        "pages": 180,
        "reviews": 15,
        "value_per_page": 0.60,
        "link": "https://www.amazon.in/dp/..."
    }
]
```

## Customization

You can modify the default wishlist URL in the `main()` function:

```python
# Default wishlist URL
default_wishlist_url = "YOUR_WISHLIST_URL_HERE"
```

## Troubleshooting

- **Selenium Errors**: Make sure you have the latest Chrome browser installed
- **GUI Not Showing**: Ensure you have Tkinter installed (included with most Python installations)
- **No Books Found**: Amazon's structure might have changed; check the console for error messages

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Disclaimer

This tool is for educational purposes only. Be respectful of Amazon's terms of service and avoid making excessive requests in a short period of time.
