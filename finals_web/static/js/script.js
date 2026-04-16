// ============================================================================
// HOME & GARDEN ECOMMERCE - GUEST HOMEPAGE FUNCTIONALITY
// ============================================================================

// Global variables
let allProducts = [];
let filteredProducts = [];
let currentPage = 1;
const productsPerPage = 12;

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initializeGuestHomepage();
});

function initializeGuestHomepage() {
    // Load products data
    loadProductsData();
    
    // Setup event listeners
    setupEventListeners();
    
    // Initialize product grid
    renderProducts();
    
    // Setup pagination
    setupPagination();
}

function loadProductsData() {
    // Products will be loaded from seller listings in the future
    // For now, initialize with empty arrays
    allProducts = [];
    filteredProducts = [];
}

function setupEventListeners() {
    // Search functionality
    const searchInput = document.querySelector('.search-input');
    if (searchInput) {
        searchInput.addEventListener('input', handleSearch);
    }
    
    // Filter functionality
    const filterSelect = document.querySelector('.filter-select');
    if (filterSelect) {
        filterSelect.addEventListener('change', handleFilter);
    }
    
    // Category functionality
    const categorySelect = document.querySelector('.category-select');
    if (categorySelect) {
        categorySelect.addEventListener('change', handleCategoryFilter);
    }
    
    // Cart button (guest restriction)
    const cartButton = document.getElementById('cartButton');
    if (cartButton) {
        cartButton.addEventListener('click', showGuestRestrictionModal);
    }
    
    // Help button
    const helpButton = document.getElementById('helpButton');
    if (helpButton) {
        helpButton.addEventListener('click', showHelpModal);
    }
    
    // Profile button (guest restriction)
    const profileBtn = document.querySelector('.profile-btn');
    if (profileBtn) {
        profileBtn.addEventListener('click', showGuestRestrictionModal);
    }
    
    // Start browsing button
    const startBrowsingBtn = document.getElementById('startBrowsing');
    if (startBrowsingBtn) {
        startBrowsingBtn.addEventListener('click', scrollToProducts);
    }
    
    // Modal close buttons
    setupModalCloseButtons();
}

function handleSearch(event) {
    const searchTerm = event.target.value.toLowerCase().trim();
    
    if (searchTerm === '') {
        filteredProducts = [...allProducts];
    } else {
        filteredProducts = allProducts.filter(product => 
            product.name.toLowerCase().includes(searchTerm) ||
            product.description.toLowerCase().includes(searchTerm) ||
            product.category.toLowerCase().includes(searchTerm)
        );
    }
    
    currentPage = 1;
    renderProducts();
    setupPagination();
}

function handleFilter(event) {
    const filterValue = event.target.value;
    
    if (filterValue === '') {
        filteredProducts = [...allProducts];
    } else if (filterValue === 'price-asc') {
        filteredProducts.sort((a, b) => a.price - b.price);
    } else if (filterValue === 'price-desc') {
        filteredProducts.sort((a, b) => b.price - a.price);
    }
    
    currentPage = 1;
    renderProducts();
    setupPagination();
}

function handleCategoryFilter(event) {
    const categoryValue = event.target.value.toLowerCase();
    
    if (categoryValue === '') {
        filteredProducts = [...allProducts];
    } else {
        filteredProducts = allProducts.filter(product => 
            product.category.toLowerCase().includes(categoryValue)
        );
    }
    
    currentPage = 1;
    renderProducts();
    setupPagination();
}

function renderProducts() {
    const productsGrid = document.getElementById('productsGrid');
    if (!productsGrid) return;
    
    const startIndex = (currentPage - 1) * productsPerPage;
    const endIndex = startIndex + productsPerPage;
    const productsToShow = filteredProducts.slice(startIndex, endIndex);
    
    if (productsToShow.length === 0) {
        productsGrid.innerHTML = `
            <div style="grid-column: 1 / -1; text-align: center; padding: 3rem; color: #6c757d;">
                <h3>No products available yet</h3>
                <p>Products from sellers will appear here soon</p>
            </div>
        `;
        return;
    }
    
    productsGrid.innerHTML = productsToShow.map(product => `
        <div class="product-card" data-product-id="${product.id}">
            <img src="${product.image || 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjgwIiBoZWlnaHQ9IjIyMCIgdmlld0JveD0iMCAwIDI4MCAyMjAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIyODAiIGhlaWdodD0iMjIwIiBmaWxsPSIjRjhGOUZBIi8+CjxwYXRoIGQ9Ik0xNDAgMTAwTDE2MCAxMjBMMTQwIDE0MEwxMjAgMTIwTDE0MCAxMDBaIiBmaWxsPSIjREREREREIi8+Cjx0ZXh0IHg9IjE0MCIgeT0iMTgwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOTk5OTk5IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiPk5vIEltYWdlPC90ZXh0Pgo8L3N2Zz4K'}" 
                 alt="${product.name}" 
                 class="product-image"
                 onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjgwIiBoZWlnaHQ9IjIyMCIgdmlld0JveD0iMCAwIDI4MCAyMjAiIGZpbGw9Im5vbmUiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+CjxyZWN0IHdpZHRoPSIyODAiIGhlaWdodD0iMjIwIiBmaWxsPSIjRjhGOUZBIi8+CjxwYXRoIGQ9Ik0xNDAgMTAwTDE2MCAxMjBMMTQwIDE0MEwxMjAgMTIwTDE0MCAxMDBaIiBmaWxsPSIjREREREREIi8+Cjx0ZXh0IHg9IjE0MCIgeT0iMTgwIiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBmaWxsPSIjOTk5OTk5IiBmb250LWZhbWlseT0iQXJpYWwiIGZvbnQtc2l6ZT0iMTQiPk5vIEltYWdlPC90ZXh0Pgo8L3N2Zz4K'">
            <div class="product-info">
                <h3 class="product-name">${product.name}</h3>
                <div class="product-price">$${product.price.toFixed(2)}</div>
                <p class="product-description">${product.description}</p>
                <button class="btn-primary" onclick="showGuestRestrictionModal()">
                    Add to Cart
                </button>
            </div>
        </div>
    `).join('');
}

function setupPagination() {
    const totalPages = Math.ceil(filteredProducts.length / productsPerPage);
    const pageNumbersContainer = document.getElementById('pageNumbers');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    
    if (!pageNumbersContainer || !prevBtn || !nextBtn) return;
    
    // Clear existing page numbers
    pageNumbersContainer.innerHTML = '';
    
    // Generate page numbers
    for (let i = 1; i <= totalPages; i++) {
        const pageBtn = document.createElement('button');
        pageBtn.textContent = i;
        pageBtn.className = `page-number ${i === currentPage ? 'active' : ''}`;
        pageBtn.addEventListener('click', () => goToPage(i));
        pageNumbersContainer.appendChild(pageBtn);
    }
    
    // Update prev/next buttons
    prevBtn.disabled = currentPage === 1;
    nextBtn.disabled = currentPage === totalPages;
    
    // Add event listeners
    prevBtn.onclick = () => goToPage(currentPage - 1);
    nextBtn.onclick = () => goToPage(currentPage + 1);
}

function goToPage(page) {
    const totalPages = Math.ceil(filteredProducts.length / productsPerPage);
    if (page >= 1 && page <= totalPages) {
        currentPage = page;
        renderProducts();
        setupPagination();
        
        // Scroll to products section
        const productsSection = document.getElementById('shop');
        if (productsSection) {
            productsSection.scrollIntoView({ behavior: 'smooth' });
        }
    }
}

function scrollToProducts() {
    const productsSection = document.getElementById('shop');
    if (productsSection) {
        productsSection.scrollIntoView({ behavior: 'smooth' });
    }
}

// ============================================================================
// GUEST RESTRICTION MODAL
// ============================================================================

function showGuestRestrictionModal() {
    const modal = document.getElementById('guestActionModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function hideGuestRestrictionModal() {
    const modal = document.getElementById('guestActionModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

// ============================================================================
// HELP MODAL
// ============================================================================

function showHelpModal() {
    const modal = document.getElementById('helpModal');
    if (modal) {
        modal.style.display = 'flex';
        document.body.style.overflow = 'hidden';
    }
}

function hideHelpModal() {
    const modal = document.getElementById('helpModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

// ============================================================================
// CART MODAL (GUEST RESTRICTION)
// ============================================================================

function showCartModal() {
    showGuestRestrictionModal();
}

function hideCartModal() {
    const modal = document.getElementById('cartModal');
    if (modal) {
        modal.style.display = 'none';
        document.body.style.overflow = 'auto';
    }
}

// ============================================================================
// MODAL MANAGEMENT
// ============================================================================

function setupModalCloseButtons() {
    // Guest action modal
    const closeGuestModal = document.getElementById('closeGuestModal');
    if (closeGuestModal) {
        closeGuestModal.addEventListener('click', hideGuestRestrictionModal);
    }
    
    // Help modal
    const closeHelpModal = document.getElementById('closeHelpModal');
    if (closeHelpModal) {
        closeHelpModal.addEventListener('click', hideHelpModal);
    }
    
    // Cart modal
    const closeCartModal = document.getElementById('closeCartModal');
    if (closeCartModal) {
        closeCartModal.addEventListener('click', hideCartModal);
    }
    
    // Close modals when clicking outside
    document.addEventListener('click', function(event) {
        if (event.target.classList.contains('modal')) {
            event.target.style.display = 'none';
            document.body.style.overflow = 'auto';
        }
    });
    
    // Close modals with Escape key
    document.addEventListener('keydown', function(event) {
        if (event.key === 'Escape') {
            const openModals = document.querySelectorAll('.modal[style*="flex"]');
            openModals.forEach(modal => {
                modal.style.display = 'none';
                document.body.style.overflow = 'auto';
            });
        }
    });
}

// ============================================================================
// UTILITY FUNCTIONS
// ============================================================================

function formatPrice(price) {
    return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency: 'USD'
    }).format(price);
}

function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// Apply debouncing to search
const debouncedSearch = debounce(handleSearch, 300);
document.querySelector('.search-input')?.addEventListener('input', debouncedSearch);

// ============================================================================
// ANIMATION HELPERS
// ============================================================================

function fadeIn(element, duration = 300) {
    element.style.opacity = '0';
    element.style.display = 'block';
    
    let start = performance.now();
    
    function animate(currentTime) {
        let elapsed = currentTime - start;
        let progress = elapsed / duration;
        
        if (progress < 1) {
            element.style.opacity = progress;
            requestAnimationFrame(animate);
        } else {
            element.style.opacity = '1';
        }
    }
    
    requestAnimationFrame(animate);
}

function fadeOut(element, duration = 300) {
    let start = performance.now();
    
    function animate(currentTime) {
        let elapsed = currentTime - start;
        let progress = elapsed / duration;
        
        if (progress < 1) {
            element.style.opacity = 1 - progress;
            requestAnimationFrame(animate);
        } else {
            element.style.display = 'none';
            element.style.opacity = '1';
        }
    }
    
    requestAnimationFrame(animate);
}