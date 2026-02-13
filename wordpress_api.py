"""
WordPress REST API integration for media upload and post assignment.
Uses WooCommerce Consumer Key/Secret for product operations.
Uses WordPress Application Password for media operations.
"""

import os
import requests
import logging
from urllib.parse import urljoin

# Load .env file for credentials
from dotenv import load_dotenv
load_dotenv()

# WordPress credentials from environment variables
WP_URL = os.environ.get('WP_URL', '')
WP_USER = os.environ.get('WP_USER', '')
WP_APP_PASSWORD = os.environ.get('WP_APP_PASSWORD', '')

# WooCommerce API credentials
WC_CONSUMER_KEY = os.environ.get('WC_CONSUMER_KEY', '')
WC_CONSUMER_SECRET = os.environ.get('WC_CONSUMER_SECRET', '')

# Create a session with proper headers
session = requests.Session()
session.headers.update({
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Accept': 'application/json',
    'Accept-Language': 'en-US,en;q=0.9',
})

def get_wp_auth():
    """Return auth tuple for WordPress REST API (media uploads)."""
    return (WP_USER, WP_APP_PASSWORD)

def get_wc_auth():
    """Return auth tuple for WooCommerce REST API (products).
    Using WP Application Password since consumer key/secret returns 401."""
    return (WP_USER, WP_APP_PASSWORD)

def is_configured():
    """Check if WordPress credentials are configured."""
    return bool(WP_URL and WP_USER and WP_APP_PASSWORD)

def get_categories():
    """
    Fetch all product categories.
    Returns a dict mapping {id: name} and {name: id}.
    """
    if not is_configured():
        logging.error("WordPress not configured")
        return {}, {}
    
    categories_by_id = {}
    categories_by_name = {}
    
    page = 1
    while True:
        try:
            url = urljoin(WP_URL, f'/wp-json/wc/v3/products/categories?per_page=100&page={page}')
            response = session.get(url, auth=get_wc_auth(), timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if not data:
                    break
                
                for cat in data:
                    c_id = cat.get('id')
                    c_name = cat.get('name')
                    categories_by_id[c_id] = c_name
                    categories_by_name[c_name.lower()] = c_id
                
                page += 1
            else:
                logging.error(f"Failed to fetch categories: {response.status_code} - {response.text[:500]}")
                break
        except Exception as e:
            logging.error(f"Exception fetching categories: {e}")
            break
            
    return categories_by_id, categories_by_name

def get_products(page=1, per_page=10, status='publish'):
    """
    Fetch products from WooCommerce.
    """
    if not is_configured():
        return []
        
    try:
        url = urljoin(WP_URL, f'/wp-json/wc/v3/products?page={page}&per_page={per_page}&status={status}')
        response = session.get(url, auth=get_wc_auth(), timeout=30)
        
        if response.status_code == 200:
            return response.json()
        else:
            logging.error(f"Failed to fetch products: {response.status_code}")
            return []
            
    except Exception as e:
        logging.error(f"Exception fetching products: {e}")
        return []

def update_product(product_id, data):
    """
    Update a product (e.g. categories).
    """
    if not is_configured():
        return False
        
    try:
        url = urljoin(WP_URL, f'/wp-json/wc/v3/products/{product_id}')
        response = session.put(url, json=data, auth=get_wc_auth(), timeout=30)
        
        if response.status_code == 200:
            logging.info(f"Updated product {product_id}")
            return True
        else:
            logging.error(f"Failed to update product {product_id}: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        logging.error(f"Exception updating product: {e}")
        return False

def check_duplicate(sku, filename=None):
    """
    Check if media already exists in WordPress by SKU or filename.
    Returns media_id if duplicate found, None otherwise.
    """
    if not WP_USER or not WP_APP_PASSWORD:
        logging.warning("WordPress not configured, skipping duplicate check")
        return None
    
    search_terms = [sku]
    if filename:
        base_name = os.path.splitext(filename)[0]
        if base_name != sku:
            search_terms.append(base_name)
    
    for term in search_terms:
        try:
            url = urljoin(WP_URL, f'/wp-json/wp/v2/media?search={term}&per_page=10')
            response = session.get(url, auth=get_wp_auth(), timeout=15)
            
            if response.status_code == 200:
                media_items = response.json()
                for item in media_items:
                    title = item.get('title', {}).get('rendered', '')
                    alt_text = item.get('alt_text', '')
                    source_url = item.get('source_url', '')
                    
                    if (sku.lower() in title.lower() or 
                        sku.lower() in alt_text.lower() or
                        sku.lower() in source_url.lower()):
                        logging.info(f"  Duplicate found: media_id={item['id']}")
                        return item['id']
        except Exception as e:
            logging.warning(f"  Duplicate check failed for '{term}': {e}")
    
    return None


def upload_media(filepath, title, alt_text=None, caption=None, description=None):
    """
    Upload image to WordPress media library.
    Returns media_id on success, None on failure.
    """
    if not WP_USER or not WP_APP_PASSWORD:
        logging.error("WordPress not configured, cannot upload")
        return None
    
    if not os.path.exists(filepath):
        logging.error(f"File not found: {filepath}")
        return None
    
    filename = os.path.basename(filepath)
    
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': 'image/jpeg'
    }
    
    try:
        url = urljoin(WP_URL, '/wp-json/wp/v2/media')
        
        with open(filepath, 'rb') as img_file:
            response = session.post(
                url,
                headers=headers,
                data=img_file.read(),
                auth=get_wp_auth(),
                timeout=60
            )
        
        if response.status_code == 201:
            media_id = response.json().get('id')
            logging.info(f"  Uploaded to WordPress: media_id={media_id}")
            update_media_metadata(media_id, title, alt_text, caption, description)
            return media_id
        else:
            logging.error(f"  Upload failed: {response.status_code} - {response.text[:200]}")
            return None
            
    except Exception as e:
        logging.error(f"  Upload exception: {e}")
        return None


def update_media_metadata(media_id, title, alt_text=None, caption=None, description=None):
    """Update media item metadata after upload."""
    if not media_id:
        return False
    
    try:
        url = urljoin(WP_URL, f'/wp-json/wp/v2/media/{media_id}')
        
        data = {
            'title': title or '',
            'alt_text': alt_text or title or '',
            'caption': caption or title or '',
            'description': description or f'Product image for {title}'
        }
        
        response = session.post(url, json=data, auth=get_wp_auth(), timeout=15)
        return response.status_code == 200
        
    except Exception as e:
        logging.warning(f"  Failed to update metadata: {e}")
        return False


def find_product_post(sku, name=None):
    """
    Find WooCommerce product post by SKU or name.
    Returns post_id if found, None otherwise.
    """
    if not is_configured():
        return None
    
    try:
        url = urljoin(WP_URL, f'/wp-json/wc/v3/products?sku={sku}')
        response = session.get(url, auth=get_wc_auth(), timeout=15)
        
        if response.status_code == 200:
            products = response.json()
            if products:
                post_id = products[0].get('id')
                logging.info(f"  Found product by SKU: post_id={post_id}")
                return post_id
    except Exception as e:
        logging.warning(f"  WooCommerce SKU search failed: {e}")
    
    if name:
        try:
            url = urljoin(WP_URL, f'/wp-json/wc/v3/products?search={name}')
            response = session.get(url, auth=get_wc_auth(), timeout=15)
            
            if response.status_code == 200:
                products = response.json()
                if products:
                    post_id = products[0].get('id')
                    logging.info(f"  Found product by name: post_id={post_id}")
                    return post_id
        except Exception as e:
            logging.warning(f"  WooCommerce name search failed: {e}")
    
    return None


def set_featured_image(post_id, media_id):
    """
    Set featured image for a WooCommerce product.
    Returns True on success, False on failure.
    """
    if not post_id or not media_id:
        return False
    
    try:
        url = urljoin(WP_URL, f'/wp-json/wc/v3/products/{post_id}')
        
        data = {
            'images': [{'id': media_id, 'position': 0}]
        }
        
        response = session.put(url, json=data, auth=get_wc_auth(), timeout=15)
        
        if response.status_code == 200:
            logging.info(f"  Set featured image: post_id={post_id}, media_id={media_id}")
            return True
        else:
            logging.warning(f"  Failed to set featured image: {response.status_code}")
            print(response.text[:200])
            return False
            
    except Exception as e:
        logging.error(f"  Set featured image exception: {e}")
        return False


    
