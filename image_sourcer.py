
import os
import pandas as pd
import requests
from rapidfuzz import fuzz
from duckduckgo_search import DDGS
import logging
import time
import re
import random
import json
from bs4 import BeautifulSoup
from fake_useragent import UserAgent

# WordPress API integration
try:
    import wordpress_api
    WP_AVAILABLE = True
except ImportError:
    WP_AVAILABLE = False

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', handlers=[
    logging.FileHandler("image_sourcer.log"),
    logging.StreamHandler()
])

INPUT_CSV = "input.csv"
OUTPUT_DIR = "product_images"
AUDIT_LOG = "image_sourcing_log.csv"

if not os.path.exists(OUTPUT_DIR):
    os.makedirs(OUTPUT_DIR)

def clean_filename(text):
    return re.sub(r'[^\w\s-]', '', str(text)).strip().replace(' ', '_')

def search_bing(query, ua):
    """Fallback search using Bing Images scraping."""
    headers = {"User-Agent": ua.random}
    # first=1 implies start at result 1
    url = f"https://www.bing.com/images/search?q={query}&form=HDRSC2&first=1"
    
    logging.info(f"  Fallback: Searching Bing for '{query}'...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        # Bing usually puts metadata in 'm' attribute of 'a' tag with class 'iusc'
        # We look for the first 5 results
        for a in soup.find_all('a', class_='iusc'):
            try:
                m = a.get('m')
                if m:
                    data = json.loads(m)
                    link = data.get('murl')
                    title = data.get('t')
                    if not title:
                        title = data.get('desc') # fallback description
                    
                    if link and title:
                        results.append({'image': link, 'title': title})
                    
                    if len(results) >= 5:
                        break
            except Exception:
                continue
                
        return results
    except Exception as e:
        logging.error(f"  Bing search failed: {e}")
        return []

def find_and_save_image(product_name, sku, ua, output_dir=OUTPUT_DIR):
    yield {'SKU': sku, 'Name': product_name, 'Status': 'Searching', 'Message': 'Starting search...'}
    
    # Sanitize product name for search query: remove * and after, trim
    search_query = product_name.split('*')[0].strip()

    # Retry Strategies
    # 1. DDG Standard
    # 2. Bing Standard (Fallback)
    # 3. DDG Broad (Backup)
    strategies = [
        {'engine': 'ddg', 'query': search_query, 'desc': 'DuckDuckGo (Standard)'},
        {'engine': 'bing', 'query': search_query, 'desc': 'Bing Images (Fallback)'},
        {'engine': 'ddg', 'query': search_query, 'desc': 'DuckDuckGo (Broad Match)'}
    ]

    for attempt, strategy in enumerate(strategies, 1):
        engine = strategy['engine']
        query = strategy['query']
        desc = strategy['desc']
        
        logging.info(f"  Attempt {attempt}/3: {desc}")
        yield {'SKU': sku, 'Name': product_name, 'Status': 'Searching', 'Message': f"Attempt {attempt}: {desc}..."}
        
        # Random delay before search
        time.sleep(random.uniform(2, 5))
        
        results = []
        try:
            if engine == 'ddg':
                with DDGS() as ddgs:
                    results = list(ddgs.images(query, max_results=5))
            elif engine == 'bing':
                results = search_bing(query, ua)
        except Exception as e:
            logging.warning(f"  {desc} failed: {e}")
            # Continue to next strategy on crash
            continue

        if not results:
            logging.info(f"  No results for strategy: {desc}")
            continue

        # Process Results
        for r in results:
            image_url = r.get('image')
            image_title = r.get('title')
            
            if not image_url or not image_title:
                 continue
            
            # Fuzzy Match at 80%
            score = fuzz.partial_ratio(product_name.lower(), image_title.lower()) if product_name else 100
            
            if score >= 80 or not product_name:
                if not product_name:
                    logging.info(f"  No product name provided. Using first result for {sku}.")
                else:
                    logging.info(f"  Match Found ({score}%). Downloading...")
                
                try:
                    status_msg = f"Downloading (SKU: {sku})" if not product_name else f"Downloading (Score: {score}%)"
                    yield {'SKU': sku, 'Name': product_name, 'Status': 'Downloading', 'Message': status_msg}
                    
                    # Random delay before download
                    time.sleep(random.uniform(1, 3))
                    
                    headers = {"User-Agent": ua.random}
                    img_data = requests.get(image_url, headers=headers, timeout=30).content
                    
                    base_name = clean_filename(product_name) if product_name else sku
                    filename = f"{base_name}.jpg"
                    filepath = os.path.join(output_dir, filename)
                    if os.path.exists(filepath):
                            filename = f"{base_name}_{sku}.jpg"
                            filepath = os.path.join(output_dir, filename)

                    with open(filepath, 'wb') as handler:
                        handler.write(img_data)
                    
                    # Success - Yield final result and Return (stop other strategies)
                    # We return the dictionary here to signal completion of this item
                    yield {'SKU': sku, 'status': 'Success', 'score': score if product_name else 100, 'file': filename, 'url': image_url, 'Name': product_name, 'Status': 'Success'}
                    return
                except Exception as e:
                    logging.warning(f"  Download failed: {e}")
                    # If download fails, maybe try next image in results? 
                    # For now we continue to next image in this result set
                    continue
            else:
                 # Low score
                 pass
        
        # If we get here, no suitable image was found in this strategy's results
        # Loop continues to next strategy

    # All strategies failed
    yield {'SKU': sku, 'status': 'Failed', 'score': 0, 'file': None, 'url': None, 'Name': product_name, 'Status': 'Failed', 'Message': 'All attempts failed'}

def main(dry_run=False):
    try:
        df = pd.read_csv(INPUT_CSV)
    except Exception as e:
        logging.error(f"Failed to read CSV: {e}")
        return

    # Check for required columns
    required_cols = ['SKU']
    for col in required_cols:
        if col not in df.columns:
            logging.error(f"Missing required column: {col}")
            return

def process_items(items, audit_log_path=AUDIT_LOG, output_dir=OUTPUT_DIR, upload_to_wordpress=False):
    """
    Generator that processes a list of items and yields results.
    items: list of dicts [{'SKU': '...', 'Name': '...'}, ...]
    upload_to_wordpress: if True, upload to WP after download
    """
    # Ensure output directory exists
    if output_dir and not os.path.exists(output_dir):
        try:
            os.makedirs(output_dir)
        except Exception as e:
            logging.error(f"Failed to create output directory '{output_dir}': {e}")
            # Fallback to default or just proceed and let save fail? 
            # Better to yield error status if we can't create dir.
            # For now, let's log and proceed, assuming find_and_save_image handles file errors.
    
    # --- State Management ---
    processed_skus = set()
    if os.path.exists(audit_log_path):
        try:
            # Try reading with flexible column handling
            existing_log = pd.read_csv(audit_log_path, on_bad_lines='skip')
            if 'SKU' in existing_log.columns:
                processed_skus = set(existing_log['SKU'].astype(str).str.strip())
            logging.info(f"Resuming... {len(processed_skus)} SKUs already processed.")
        except Exception as e:
            logging.warning(f"Could not read existing log file, starting fresh. Error: {e}")


    # Initialize UserAgent
    ua = UserAgent()

    for index, row in enumerate(items):
        sku = str(row.get('SKU', '')).strip()
        name = str(row.get('Name', '')).strip()
        
        has_existing_image = row.get('HasImage', False)
        
        # Filesystem check - look for sku.jpg or name.jpg
        # We check both to be safe
        possible_filenames = [f"{sku}.jpg", f"{clean_filename(name)}.jpg" if name else None]
        for pf in possible_filenames:
            if pf and os.path.exists(os.path.join(output_dir, pf)):
                has_existing_image = True
                break

        # Skip if already processed (log) or has existing image (CSV/Disk)
        if sku in processed_skus or has_existing_image:
            reason = 'Already processed in log' if sku in processed_skus else 'Image already exists'
            yield {'SKU': sku, 'Name': name, 'Status': 'Skipped', 'Message': reason}
            continue

        if not name or name.lower() == 'nan':
            logging.info(f"Row {index}: Missing Name, will search by SKU {sku} only")
            name = ""

        # Pass user agent instance
        # process generator
        final_result = None
        for update in find_and_save_image(name, sku, ua, output_dir=output_dir):
            # Pass through intermediate updates to UI
            yield update
            
            # Check if this is a final result
            if update.get('Status') in ['Success', 'Failed']:
                final_result = update
        
        if not final_result:
             # Should not happen given logic, but safety fallback
             final_result = {'SKU': sku, 'Name': name, 'Status': 'Failed', 'Message': 'Unknown error'}
             yield final_result

        # WordPress integration after successful download
        wp_media_id = None
        wp_status = 'Not Uploaded'
        wp_duplicate = False
        
        if upload_to_wordpress and WP_AVAILABLE and final_result.get('Status') == 'Success':
            filepath = os.path.join(output_dir, final_result.get('file', ''))
            filename = final_result.get('file', '')
            
            # Check for duplicate in WordPress
            yield {'SKU': sku, 'Name': name, 'Status': 'Checking WordPress', 'Message': 'Checking for duplicates...'}
            existing_id = wordpress_api.check_duplicate(sku, filename)
            
            if existing_id:
                # Duplicate found - reuse existing media
                wp_media_id = existing_id
                wp_status = 'Skipped (Duplicate)'
                wp_duplicate = True
                yield {'SKU': sku, 'Name': name, 'Status': 'Skipped (Duplicate)', 'Message': f'Reusing media ID {existing_id}'}
            else:
                # Upload to WordPress
                yield {'SKU': sku, 'Name': name, 'Status': 'Uploading to WordPress', 'Message': 'Uploading...'}
                wp_media_id = wordpress_api.upload_media(
                    filepath,
                    title=name or sku,
                    alt_text=name or sku,
                    caption=name or sku,
                    description=f'Product image for {name or sku}'
                )
                
                if wp_media_id:
                    wp_status = 'Uploaded'
                    
                    # Find and assign to product
                    yield {'SKU': sku, 'Name': name, 'Status': 'Assigning Image', 'Message': 'Finding product...'}
                    post_id = wordpress_api.find_product_post(sku, name)
                    
                    if post_id:
                        if wordpress_api.set_featured_image(post_id, wp_media_id):
                            wp_status = 'Assigned'
                            yield {'SKU': sku, 'Name': name, 'Status': 'Assigned', 'Message': f'Assigned to product {post_id}'}
                        else:
                            wp_status = 'Upload OK, Assign Failed'
                    else:
                        wp_status = 'Uploaded (No Product Found)'
                        yield {'SKU': sku, 'Name': name, 'Status': 'Uploaded', 'Message': 'No matching product found'}
                else:
                    wp_status = 'Upload Failed'
                    yield {'SKU': sku, 'Name': name, 'Status': 'Failed', 'Message': 'WordPress upload failed'}

        # Immediate logging to file for robustness
        log_entry = {
            'SKU': sku,
            'Original Name': name,
            'Similarity Score': final_result.get('score', 0),
            'Image Source URL': final_result.get('url', ''),
            'Saved Filename': final_result.get('file', ''),
            'Status': final_result['Status'],
            'WP Media ID': wp_media_id or '',
            'WP Upload Status': wp_status,
            'WP Duplicate': wp_duplicate
        }
        
        # Append to CSV immediately
        try:
            log_df = pd.DataFrame([log_entry])
            header = not os.path.exists(audit_log_path)
            log_df.to_csv(audit_log_path, mode='a', header=header, index=False)
        except Exception as e:
            logging.error(f"Failed to write to audit log: {e}")
        
        # Polite randomized delay between SKUs (3-7s)
        delay = random.uniform(3, 7)
        # Yield a status update about the delay
        yield {'SKU': sku, 'Name': name, 'Status': 'Waiting', 'Message': "downloaded"}
        logging.info(f"Sleeping for {delay:.2f} seconds...")
        time.sleep(delay)

def main(dry_run=False):
    try:
        df = pd.read_csv(INPUT_CSV)
    except Exception as e:
        logging.error(f"Failed to read CSV: {e}")
        return

    # Check for required columns
    required_cols = ['SKU']
    for col in required_cols:
        if col not in df.columns:
            logging.error(f"Missing required column: {col}")
            return
            
    items = df.to_dict('records')
    if dry_run:
        items = items[:5]

    for result in process_items(items):
        print(f"Processed {result['SKU']}: {result['Status']}")

    logging.info(f"Process complete.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run only first 5 items")
    args = parser.parse_args()
    main(dry_run=args.dry_run)
