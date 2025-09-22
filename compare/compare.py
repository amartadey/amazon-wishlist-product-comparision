import json

def compare_prices(old_file_path, new_file_path):
    """
    Compares the prices of books between two JSON files and identifies those
    whose prices have decreased.

    Args:
        old_file_path (str): The path to the JSON file with older price data.
        new_file_path (str): The path to the JSON file with newer price data.

    Returns:
        list: A list of dictionaries for books with decreased prices.
              Returns an empty list if any file fails to load or no prices have decreased.
    """
    try:
        with open(old_file_path, 'r') as f:
            old_data = json.load(f)
        with open(new_file_path, 'r') as f:
            new_data = json.load(f)
    except FileNotFoundError:
        print("Error: One of the input files was not found.")
        return []
    except json.JSONDecodeError:
        print("Error: Could not decode one of the JSON files.")
        return []

    old_prices = {item['asin']: item for item in old_data}
    decreased_prices = []

    for new_book in new_data:
        asin = new_book.get('asin')
        new_price = new_book.get('price')

        # Check if the book existed in the old data and has a valid price
        if asin in old_prices and new_price is not None:
            old_book = old_prices[asin]
            old_price = old_book.get('price')

            # Only proceed if the old price is also valid and greater than the new price
            if old_price is not None and new_price < old_price:
                price_decrease = old_price - new_price
                
                # Calculate percentage decrease if both prices are not zero
                percentage_decrease = 0
                if old_price > 0:
                    percentage_decrease = (price_decrease / old_price) * 100

                book_info = {
                    'title': new_book.get('title'),
                    'author': new_book.get('author'),
                    'asin': asin,
                    'link': new_book.get('link'),
                    'new_price': new_price,
                    'old_price': old_price,
                    'price_decrease_abs': round(price_decrease, 2),
                    'price_decrease_perc': round(percentage_decrease, 2),
                    'pages': new_book.get('pages'),
                    'reviews': new_book.get('reviews'),
                    'avg_rating': new_book.get('avg_rating'),
                    'wishlist_name': new_book.get('wishlist_name'),
                    'format': new_book.get('format'),
                }
                decreased_prices.append(book_info)

    return decreased_prices

def save_to_json(data, output_file_path):
    """Saves a list of dictionaries to a JSON file."""
    with open(output_file_path, 'w') as f:
        json.dump(data, f, indent=4)

if __name__ == "__main__":
    # Define file paths
    old_file = 'old.json'
    new_file = 'new.json'
    output_file = 'decreased_prices.json'

    # Run the comparison and save the results
    result_list = compare_prices(old_file, new_file)
    if result_list:
        save_to_json(result_list, output_file)
        print(f"Successfully saved {len(result_list)} books with decreased prices to '{output_file}'.")
    else:
        print("No price decreases found or an error occurred.")
