"""
LosHusan Supermarket Product Image Scraper
==========================================
A robust script to download product images from https://loshusansupermarket.com/products/

Features:
- Recursive crawling through categories
- Filters out UI elements (logos, icons, navigation)
- Saves images with product names
- Error handling and polite delays
- Uses Playwright for JavaScript-rendered content

Requirements:
    pip install playwright beautifulsoup4 requests
    playwright install chromium
"""

import os
import re
import time
import hashlib
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# Try to import playwright, fall back to requests-only mode if not available
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("  Playwright not installed. Using requests-only mode.")
    print("   For JavaScript-heavy sites, install with: pip install playwright && playwright install chromium")

# Configuration
BASE_URL = "https://loshusansupermarket.com"
PRODUCTS_URL = f"{BASE_URL}/products/"
OUTPUT_DIR = "loshusan_inventory"
DELAY_BETWEEN_REQUESTS = 1.5  # seconds - be polite to the server
REQUEST_TIMEOUT = 30

# Common UI elements to filter out
UI_FILTER_PATTERNS = [
    r'logo', r'icon', r'arrow', r'cart', r'search', r'menu',
    r'facebook', r'twitter', r'instagram', r'pinterest', r'youtube',
    r'social', r'banner', r'placeholder', r'loading', r'spinner',
    r'button', r'nav', r'footer', r'header', r'avatar',
    r'close', r'expand', r'collapse', r'chevron', r'caret'
]

# Product-related URL patterns that suggest it's a product image
PRODUCT_URL_PATTERNS = [
    r'/products/', r'/categories/', r'/product-images/',
    r'/uploads/', r'/media/', r'/images/products'
]


def clean_filename(text):
    """Clean text to create a valid filename."""
    if not text:
        return None
    # Remove special characters, keep alphanumeric, spaces, hyphens
    cleaned = re.sub(r'[^\w\s-]', '', str(text)).strip()
    cleaned = re.sub(r'\s+', '_', cleaned)
    return cleaned[:100]  # Limit length


def get_filename_from_url(url):
    """Extract a clean filename from URL."""
    parsed = urlparse(url)
    path = parsed.path
    # Get the last part of the path
    filename = os.path.basename(path)
    # Remove query strings
    filename = filename.split('?')[0]
    return filename


def is_product_image(img_url, alt_text=""):
    """Determine if an image is likely a product image vs UI element."""
    url_lower = img_url.lower()
    alt_lower = alt_text.lower() if alt_text else ""
    
    # Filter out UI elements
    for pattern in UI_FILTER_PATTERNS:
        if re.search(pattern, url_lower) or re.search(pattern, alt_lower):
            return False
    
    # Check for very small images (likely icons)
    # These patterns suggest icon sizes
    if re.search(r'[_-](16|20|24|32|48)x', url_lower):
        return False
    if re.search(r'icon[_-]?\d+', url_lower):
        return False
    
    # Check for product-related URL patterns
    for pattern in PRODUCT_URL_PATTERNS:
        if re.search(pattern, url_lower):
            return True
    
    # If it has a meaningful alt text that's not too short, likely a product
    if alt_text and len(alt_text) > 5:
        return True
    
    # Check file extension
    valid_extensions = ['.jpg', '.jpeg', '.png', '.webp', '.gif']
    if any(url_lower.endswith(ext) for ext in valid_extensions):
        return True
    
    return False


def download_image(url, filepath, session=None):
    """Download an image and save it to filepath."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/webp,image/apng,image/*,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Referer': BASE_URL
        }
        
        if session:
            response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
        else:
            response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT, stream=True)
        
        if response.status_code == 200:
            content_type = response.headers.get('content-type', '')
            if 'image' in content_type or any(url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.webp', '.gif']):
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                return True
        else:
            print(f"   HTTP {response.status_code} for {url}")
    except requests.exceptions.Timeout:
        print(f"   Timeout downloading: {url}")
    except requests.exceptions.RequestException as e:
        print(f"   Error downloading {url}: {e}")
    except Exception as e:
        print(f"   Unexpected error: {e}")
    
    return False


def get_page_with_playwright(url):
    """Fetch page content using Playwright (handles JavaScript)."""
    if not PLAYWRIGHT_AVAILABLE:
        return None
    
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                viewport={'width': 1920, 'height': 1080}
            )
            page = context.new_page()
            
            # Navigate and wait for network to be idle
            page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Scroll to load lazy images
            page.evaluate("""
                () => {
                    window.scrollTo(0, document.body.scrollHeight);
                }
            """)
            time.sleep(2)  # Wait for lazy-loaded content
            
            content = page.content()
            browser.close()
            return content
    except Exception as e:
        print(f"   Playwright error for {url}: {e}")
        return None


def get_page_with_requests(url, session):
    """Fetch page content using requests (static content only)."""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1'
        }
        response = session.get(url, headers=headers, timeout=REQUEST_TIMEOUT)
        if response.status_code == 200:
            return response.text
        else:
            print(f"   HTTP {response.status_code} for {url}")
    except Exception as e:
        print(f"   Request error for {url}: {e}")
    return None


def extract_category_links(soup, base_url):
    """Extract category/section links from the page."""
    categories = set()
    
    # Common patterns for category links
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        text = link.get_text(strip=True).lower()
        
        # Look for category-like links
        if any(pattern in href.lower() for pattern in ['/category', '/products/', '/collection', '/department']):
            full_url = urljoin(base_url, href)
            if full_url.startswith(base_url):  # Stay on same domain
                categories.add(full_url)
        
        # Also check link text for category indicators
        category_keywords = ['dairy', 'frozen', 'meat', 'produce', 'bakery', 'beverages', 
                           'snacks', 'grocery', 'household', 'seafood', 'deli', 'organic']
        if any(keyword in text for keyword in category_keywords):
            full_url = urljoin(base_url, href)
            if full_url.startswith(base_url):
                categories.add(full_url)
    
    return list(categories)


def extract_product_images(soup, page_url):
    """Extract product images from the page."""
    images = []
    
    # Strategy 1: Look for images within product containers
    product_containers = soup.find_all(['div', 'article', 'li'], 
                                        class_=re.compile(r'product|item|card', re.I))
    
    for container in product_containers:
        for img in container.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                alt = img.get('alt', '')
                full_url = urljoin(page_url, src)
                if is_product_image(full_url, alt):
                    images.append({'url': full_url, 'alt': alt})
    
    # Strategy 2: Look for all images with product-related URLs
    if not images:
        for img in soup.find_all('img'):
            src = img.get('src') or img.get('data-src') or img.get('data-lazy-src')
            if src:
                alt = img.get('alt', '')
                full_url = urljoin(page_url, src)
                if is_product_image(full_url, alt):
                    images.append({'url': full_url, 'alt': alt})
    
    # Strategy 3: Look for background images in style attributes
    for elem in soup.find_all(style=True):
        style = elem.get('style', '')
        urls = re.findall(r'url\([\'"]?([^\'"]+)[\'"]?\)', style)
        for url in urls:
            full_url = urljoin(page_url, url)
            if is_product_image(full_url):
                images.append({'url': full_url, 'alt': ''})
    
    return images


def scrape_page(url, session, use_playwright=True):
    """Scrape a single page for images."""
    print(f"\n Scraping: {url}")
    
    # Try Playwright first (better for JS-heavy sites)
    content = None
    if use_playwright and PLAYWRIGHT_AVAILABLE:
        content = get_page_with_playwright(url)
    
    # Fall back to requests
    if not content:
        content = get_page_with_requests(url, session)
    
    if not content:
        print(f"   Could not fetch page content")
        return [], []
    
    soup = BeautifulSoup(content, 'html.parser')
    
    # Extract data
    categories = extract_category_links(soup, BASE_URL)
    images = extract_product_images(soup, url)
    
    print(f"   Found {len(categories)} category links")
    print(f"   Found {len(images)} product images")
    
    return categories, images


def main():
    """Main scraping function."""
    print("=" * 60)
    print(" LosHusan Supermarket Product Image Scraper")
    print("=" * 60)
    
    # Create output directory
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        print(f"\n Created output directory: {OUTPUT_DIR}")
    
    # Track what we've processed
    visited_urls = set()
    downloaded_images = set()
    all_images = []
    
    # Create session for connection pooling
    session = requests.Session()
    
    # Start with the main products page
    urls_to_visit = [PRODUCTS_URL]
    
    # Phase 1: Discover categories
    print("\n" + "=" * 60)
    print("Phase 1: Discovering Categories")
    print("=" * 60)
    
    while urls_to_visit:
        url = urls_to_visit.pop(0)
        
        if url in visited_urls:
            continue
        
        visited_urls.add(url)
        
        try:
            categories, images = scrape_page(url, session, use_playwright=True)
            all_images.extend(images)
            
            # Add new categories to visit
            for cat_url in categories:
                if cat_url not in visited_urls:
                    urls_to_visit.append(cat_url)
            
            # Be polite
            time.sleep(DELAY_BETWEEN_REQUESTS)
            
        except Exception as e:
            print(f"   Error processing {url}: {e}")
            continue
    
    print(f"\n Discovered {len(visited_urls)} pages")
    print(f" Found {len(all_images)} total images")
    
    # Phase 2: Download images
    print("\n" + "=" * 60)
    print("Phase 2: Downloading Images")
    print("=" * 60)
    
    download_count = 0
    skip_count = 0
    error_count = 0
    
    for idx, img_data in enumerate(all_images, 1):
        url = img_data['url']
        alt = img_data['alt']
        
        # Skip duplicates
        if url in downloaded_images:
            skip_count += 1
            continue
        
        downloaded_images.add(url)
        
        # Generate filename
        if alt:
            filename = clean_filename(alt)
        else:
            filename = clean_filename(get_filename_from_url(url))
        
        if not filename:
            # Use hash of URL as fallback
            filename = hashlib.md5(url.encode()).hexdigest()[:12]
        
        # Determine extension
        url_lower = url.lower()
        if '.png' in url_lower:
            ext = '.png'
        elif '.webp' in url_lower:
            ext = '.webp'
        elif '.gif' in url_lower:
            ext = '.gif'
        else:
            ext = '.jpg'
        
        filepath = os.path.join(OUTPUT_DIR, f"{filename}{ext}")
        
        # Handle duplicate filenames
        counter = 1
        while os.path.exists(filepath):
            filepath = os.path.join(OUTPUT_DIR, f"{filename}_{counter}{ext}")
            counter += 1
        
        print(f"  [{idx}/{len(all_images)}] Downloading: {filename}{ext}")
        
        if download_image(url, filepath, session):
            download_count += 1
        else:
            error_count += 1
        
        # Be polite
        time.sleep(DELAY_BETWEEN_REQUESTS / 2)
    
    # Summary
    print("\n" + "=" * 60)
    print(" Summary")
    print("=" * 60)
    print(f"  Pages visited:     {len(visited_urls)}")
    print(f"  Images found:      {len(all_images)}")
    print(f"  Images downloaded: {download_count}")
    print(f"  Duplicates skipped: {skip_count}")
    print(f"  Errors:            {error_count}")
    print(f"\n  Images saved to: {os.path.abspath(OUTPUT_DIR)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
