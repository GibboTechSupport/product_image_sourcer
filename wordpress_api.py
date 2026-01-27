"""
WordPress REST API integration for media upload and post assignment.
Uses Application Passwords for authentication.
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


def get_auth():
    """Return auth tuple for WordPress REST API."""
    return (WP_USER, WP_APP_PASSWORD)


def is_configured():
    """Check if WordPress credentials are configured."""
    return bool(WP_URL and WP_USER and WP_APP_PASSWORD)


def check_duplicate(sku, filename=None):
    """
    Check if media already exists in WordPress by SKU or filename.
    Returns media_id if duplicate found, None otherwise.
    """
    if not is_configured():
        logging.warning("WordPress not configured, skipping duplicate check")
        return None
    
    search_terms = [sku]
    if filename:
        # Remove extension for search
        base_name = os.path.splitext(filename)[0]
        if base_name != sku:
            search_terms.append(base_name)
    
    for term in search_terms:
        try:
            url = urljoin(WP_URL, f'/wp-json/wp/v2/media?search={term}&per_page=10')
            response = requests.get(url, auth=get_auth(), timeout=15)
            
            if response.status_code == 200:
                media_items = response.json()
                for item in media_items:
                    # Check title, alt_text, or filename match
                    title = item.get('title', {}).get('rendered', '')
                    alt_text = item.get('alt_text', '')
                    source_url = item.get('source_url', '')
                    
                    # Match by SKU in title/alt or filename
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
    if not is_configured():
        logging.error("WordPress not configured, cannot upload")
        return None
    
    if not os.path.exists(filepath):
        logging.error(f"File not found: {filepath}")
        return None
    
    filename = os.path.basename(filepath)
    
    # Prepare headers
    headers = {
        'Content-Disposition': f'attachment; filename="{filename}"',
        'Content-Type': 'image/jpeg'
    }
    
    try:
        url = urljoin(WP_URL, '/wp-json/wp/v2/media')
        
        with open(filepath, 'rb') as img_file:
            response = requests.post(
                url,
                headers=headers,
                data=img_file.read(),
                auth=get_auth(),
                timeout=60
            )
        
        if response.status_code == 201:
            media_id = response.json().get('id')
            logging.info(f"  Uploaded to WordPress: media_id={media_id}")
            
            # Update metadata (title, alt_text, caption, description)
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
        
        response = requests.post(url, json=data, auth=get_auth(), timeout=15)
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
    
    # Try WooCommerce products endpoint first (by SKU)
    try:
        url = urljoin(WP_URL, f'/wp-json/wc/v3/products?sku={sku}')
        response = requests.get(url, auth=get_auth(), timeout=15)
        
        if response.status_code == 200:
            products = response.json()
            if products:
                post_id = products[0].get('id')
                logging.info(f"  Found product by SKU: post_id={post_id}")
                return post_id
    except Exception as e:
        logging.warning(f"  WooCommerce SKU search failed: {e}")
    
    # Fallback: search by name
    if name:
        try:
            url = urljoin(WP_URL, f'/wp-json/wc/v3/products?search={name}')
            response = requests.get(url, auth=get_auth(), timeout=15)
            
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
        
        response = requests.put(url, json=data, auth=get_auth(), timeout=15)
        
        if response.status_code == 200:
            logging.info(f"  Set featured image: post_id={post_id}, media_id={media_id}")
            return True
        else:
            logging.warning(f"  Failed to set featured image: {response.status_code}")
            return False
            
    except Exception as e:
        logging.error(f"  Set featured image exception: {e}")
        return False
