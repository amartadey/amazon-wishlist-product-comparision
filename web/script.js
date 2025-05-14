// Main JavaScript file for Amazon Books Finder

document.addEventListener('DOMContentLoaded', () => {
  // Global variables
  let booksData = [];
  let filteredBooks = [];
  
  // DOM elements
  const booksContainer = document.getElementById('books-container');
  const bookCount = document.getElementById('book-count');
  const noResults = document.getElementById('no-results');
  const searchInput = document.getElementById('search');
  const minPriceInput = document.getElementById('min-price');
  const maxPriceInput = document.getElementById('max-price');
  const minPagesInput = document.getElementById('min-pages');
  const maxPagesInput = document.getElementById('max-pages');
  const minReviewsInput = document.getElementById('min-reviews');
  const sortBySelect = document.getElementById('sort-by');
  const filterBtn = document.getElementById('filter-btn');
  const resetBtn = document.getElementById('reset-btn');

  // Fetch book data from JSON file
  async function fetchBooks() {
    try {
      const response = await fetch('amazon_books.json');
      if (!response.ok) {
        throw new Error('Network response was not ok');
      }
      booksData = await response.json();
      
      // Initial display
      filteredBooks = [...booksData];
      displayBooks(filteredBooks);
      updateBookCount(filteredBooks.length);
      populateFilterRanges();
    } catch (error) {
      console.error('Error fetching book data:', error);
      booksContainer.innerHTML = `
        <div class="col-12">
          <div class="alert alert-danger">
            <span class="iconify" data-icon="mdi:alert-circle" data-width="24"></span>
            Failed to load books data. Please try refreshing the page.
          </div>
        </div>
      `;
    }
  }

  // Populate filter range inputs with min/max values
  function populateFilterRanges() {
    if (booksData.length === 0) return;
    
    // Calculate min/max values for price, pages, and reviews
    const prices = booksData.filter(book => book.price !== null).map(book => book.price);
    const pages = booksData.filter(book => book.pages !== null).map(book => book.pages);
    const reviews = booksData.filter(book => book.reviews !== null).map(book => book.reviews);
    
    // Set placeholder values
    minPriceInput.placeholder = Math.min(...prices) || 0;
    maxPriceInput.placeholder = Math.max(...prices) || 0;
    minPagesInput.placeholder = Math.min(...pages) || 0;
    maxPagesInput.placeholder = Math.max(...pages) || 0;
    minReviewsInput.placeholder = Math.min(...reviews) || 0;
  }
  
  // Display books in the container
  function displayBooks(books) {
    if (books.length === 0) {
      booksContainer.innerHTML = '';
      noResults.classList.remove('d-none');
      return;
    }
    
    noResults.classList.add('d-none');
    booksContainer.innerHTML = books.map(book => createBookCard(book)).join('');
  }
  
  // Create HTML for a book card
  function createBookCard(book) {
    // Format value calculation and display
    const valueFormatted = book.value_per_page !== null ? 
                          `₹${book.value_per_page.toFixed(2)} per page` : 
                          'N/A';
    
    // Determine value rating (good, average, poor)
    let valueRatingClass = 'text-muted';
    let valueIcon = 'mdi:minus';
    
    if (book.value_per_page !== null) {
      if (book.value_per_page < 0.8) {
        valueRatingClass = 'text-success';
        valueIcon = 'mdi:thumb-up';
      } else if (book.value_per_page < 1) {
        valueRatingClass = 'text-warning';
        valueIcon = 'mdi:hand-okay';
      } else {
        valueRatingClass = 'text-danger';
        valueIcon = 'mdi:thumb-down';
      }
    }
    
    return `
      <div class="col-md-6 col-lg-4 mb-4">
        <div class="card h-100 book-card">
          <div class="card-header">
            <h5 class="card-title text-truncate" title="${book.title}">
              ${book.title}
            </h5>
          </div>
          <div class="card-body">
            <div class="book-details">
              <div class="detail-item">
                <span class="iconify" data-icon="mdi:currency-inr" data-width="18"></span>
                <span class="detail-label">Price:</span>
                <span class="detail-value">${book.price !== null ? `₹${book.price}` : 'N/A'}</span>
              </div>
              
              <div class="detail-item">
                <span class="iconify" data-icon="mdi:book-open-page-variant" data-width="18"></span>
                <span class="detail-label">Pages:</span>
                <span class="detail-value">${book.pages !== null ? book.pages : 'N/A'}</span>
              </div>
              
              <div class="detail-item">
                <span class="iconify" data-icon="mdi:star" data-width="18"></span>
                <span class="detail-label">Reviews:</span>
                <span class="detail-value">${book.reviews !== null ? book.reviews.toLocaleString() : 'N/A'}</span>
              </div>
              
              <div class="detail-item ${valueRatingClass}">
                <span class="iconify" data-icon="${valueIcon}" data-width="18"></span>
                <span class="detail-label">Value:</span>
                <span class="detail-value">${valueFormatted}</span>
              </div>
            </div>
          </div>
          <div class="card-footer">
            <a href="${book.link}" class="btn btn-primary btn-sm w-100" target="_blank">
              <span class="iconify" data-icon="mdi:shopping" data-width="20"></span>
              View on Amazon
            </a>
          </div>
        </div>
      </div>
    `;
  }
  
  // Update book count display
  function updateBookCount(count) {
    bookCount.textContent = count;
  }
  
  // Apply filters to the book data
  function applyFilters() {
    const searchTerm = searchInput.value.toLowerCase().trim();
    const minPrice = minPriceInput.value ? parseFloat(minPriceInput.value) : null;
    const maxPrice = maxPriceInput.value ? parseFloat(maxPriceInput.value) : null;
    const minPages = minPagesInput.value ? parseInt(minPagesInput.value) : null;
    const maxPages = maxPagesInput.value ? parseInt(maxPagesInput.value) : null;
    const minReviews = minReviewsInput.value ? parseInt(minReviewsInput.value) : null;
    
    filteredBooks = booksData.filter(book => {
      // Search by title
      if (searchTerm && (!book.title || !book.title.toLowerCase().includes(searchTerm))) {
        return false;
      }
      
      // Filter by price
      if (minPrice !== null && (book.price === null || book.price < minPrice)) {
        return false;
      }
      if (maxPrice !== null && (book.price === null || book.price > maxPrice)) {
        return false;
      }
      
      // Filter by pages
      if (minPages !== null && (book.pages === null || book.pages < minPages)) {
        return false;
      }
      if (maxPages !== null && (book.pages === null || book.pages > maxPages)) {
        return false;
      }
      
      // Filter by reviews
      if (minReviews !== null && (book.reviews === null || book.reviews < minReviews)) {
        return false;
      }
      
      return true;
    });
    
    // Apply sorting
    sortBooks();
    
    // Update UI
    displayBooks(filteredBooks);
    updateBookCount(filteredBooks.length);
  }
  
  // Sort books based on selected criteria
  function sortBooks() {
    const sortBy = sortBySelect.value;
    
    switch (sortBy) {
      case 'title':
        filteredBooks.sort((a, b) => {
          if (!a.title) return 1;
          if (!b.title) return -1;
          return a.title.localeCompare(b.title);
        });
        break;
        
      case 'price-low':
        filteredBooks.sort((a, b) => {
          if (a.price === null) return 1;
          if (b.price === null) return -1;
          return a.price - b.price;
        });
        break;
        
      case 'price-high':
        filteredBooks.sort((a, b) => {
          if (a.price === null) return 1;
          if (b.price === null) return -1;
          return b.price - a.price;
        });
        break;
        
      case 'pages':
        filteredBooks.sort((a, b) => {
          if (a.pages === null) return 1;
          if (b.pages === null) return -1;
          return a.pages - b.pages;
        });
        break;
        
      case 'reviews':
        filteredBooks.sort((a, b) => {
          if (a.reviews === null) return 1;
          if (b.reviews === null) return -1;
          return b.reviews - a.reviews;
        });
        break;
        
      case 'value':
        filteredBooks.sort((a, b) => {
          if (a.value_per_page === null) return 1;
          if (b.value_per_page === null) return -1;
          return a.value_per_page - b.value_per_page;
        });
        break;
    }
  }
  
  // Reset all filters
  function resetFilters() {
    searchInput.value = '';
    minPriceInput.value = '';
    maxPriceInput.value = '';
    minPagesInput.value = '';
    maxPagesInput.value = '';
    minReviewsInput.value = '';
    sortBySelect.value = 'title';
    
    filteredBooks = [...booksData];
    displayBooks(filteredBooks);
    updateBookCount(filteredBooks.length);
  }
  
  // Event listeners
  filterBtn.addEventListener('click', applyFilters);
  resetBtn.addEventListener('click', resetFilters);
  
  // Enable search on Enter key
  searchInput.addEventListener('keyup', (e) => {
    if (e.key === 'Enter') {
      applyFilters();
    }
  });
  
  // Input debounce function for real-time filtering
  function debounce(func, wait) {
    let timeout;
    return function(...args) {
      clearTimeout(timeout);
      timeout = setTimeout(() => func.apply(this, args), wait);
    };
  }
  
  // Apply real-time filtering on input changes (debounced)
  const debouncedFilter = debounce(applyFilters, 300);
  
  // Optional: Add event listeners for real-time filtering
  searchInput.addEventListener('input', debouncedFilter);
  minPriceInput.addEventListener('input', debouncedFilter);
  maxPriceInput.addEventListener('input', debouncedFilter);
  minPagesInput.addEventListener('input', debouncedFilter);
  maxPagesInput.addEventListener('input', debouncedFilter);
  minReviewsInput.addEventListener('input', debouncedFilter);
  sortBySelect.addEventListener('change', debouncedFilter);
  
  // Initialize the application
  fetchBooks();
});