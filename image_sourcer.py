
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
import traceback
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




def search_google(query, ua):
    """Fallback search using Google Images scraping."""
    headers = {"User-Agent": ua.random}
    url = f"https://www.google.com/search?tbm=isch&q={query} "


    logging.info(f"  Fallback: Searching Google for '{query}'...")
    try:
        response = requests.get(url, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        results = []
        # Google usually puts metadata in 'data-src' or 'src' attributes of 'img' tags
        for img in soup.find_all('img'):
            link = img.get('data-src') or img.get('src')
            title = img.get('alt')
            if link and title:
                results.append({'image': link, 'title': title})
            
            if len(results) >= 5:
                break
                
        return results
    except Exception as e:
        logging.error(f"  Google search failed: {e}")
        return []

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
    search_query = product_name.split('*, %')[0].strip()

    # Retry Strategies
    # 1. DDG Standard
    # 2. Bing Standard (Fallback)
    # 3. DDG Broad (Backup)
    strategies = [
        {'engine': 'ddg', 'query': search_query, 'desc': 'DuckDuckGo (Standard)'},
        {'engine': 'bing', 'query': search_query, 'desc': 'Bing Images (Fallback)'},
        {'engine': 'google', 'query': search_query, 'desc': 'Google Images (Fallback)'},
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

        # Process Results - Find Best Match
        best_candidate = None
        best_score = 0

        for r in results:
            image_url = r.get('image')
            image_title = r.get('title')
            
            if not image_url or not image_title:
                 continue
            
            # Fuzzy Match using token_set_ratio for better accuracy with reordered words
            # e.g. "Apple Juice" matches "Juice Apple"
            score = fuzz.token_set_ratio(product_name.lower(), image_title.lower()) if product_name else 100
            
            if score >= 70 or not product_name:
                logging.info(f"  Candidate found: {score}% - {image_title[:30]}...")
                if score > best_score:
                    best_score = score
                    best_candidate = r
                    best_candidate['score'] = score # Store score in result
            else:
                 # Low score
                 pass
        
        # Check if we found a suitable candidate in this strategy
        if best_candidate:
            image_url = best_candidate.get('image')
            image_title = best_candidate.get('title')
            score = best_candidate.get('score', 0)

            if not product_name:
                logging.info(f"  No product name provided. Using first result for {sku}.")
            else:
                logging.info(f"  BEST MATCH Found ({score}%): {image_title}")
            
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
                    logging.info(f"  Writing image file to {filepath}")
                    handler.write(img_data)
                    logging.info(f"  Image file written successfully")
                
                # Success - Yield final result and Return (stop other strategies)
                # We return the dictionary here to signal completion of this item
                yield {'SKU': sku, 'status': 'Success', 'score': score if product_name else 100, 'file': filename, 'url': image_url, 'Name': product_name, 'Status': 'Success'}
                return
            except Exception as e:
                logging.warning(f"  Download failed: {e}")
                # If download matches failed, we might want to try the NEXT best match?
                # For now, if the best match fails to download, we continue to the next strategy
                continue
        
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
            if 'SKU' in existing_log.columns and 'Status' in existing_log.columns:
                # Only skip SKUs that were successfully processed
                success_mask = existing_log['Status'] == 'Success'
                processed_skus = set(existing_log.loc[success_mask, 'SKU'].astype(str).str.strip())
            elif 'SKU' in existing_log.columns:
                # Fallback if Status column missing (legacy logs)
                processed_skus = set(existing_log['SKU'].astype(str).str.strip())
            logging.info(f"Resuming... {len(processed_skus)} SKUs already successfully processed.")
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
        
        try:
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
        except Exception as e:
            logging.error(f"Error in WordPress integration: {e}\n{traceback.format_exc()}")
            yield {'SKU': sku, 'Name': name, 'Status': 'Error', 'Message': f"WP Error: {str(e)}"}

        # Immediate logging to file for robustness
        log_entry = {
            'SKU': sku,
            'Original Name': name,
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
            logging.info(f"  Writing to audit log (Append Mode)...")
            log_df.to_csv(audit_log_path, mode='a', header=header, index=False)
            logging.info(f"  Audit log written successfully")
        except Exception as e:
            logging.error(f"Failed to write to audit log: {e}")
        
        # Polite randomized delay between SKUs (3-7s)
        delay = random.uniform(3, 7)
def update_csv_with_urls(input_csv_path=INPUT_CSV, audit_log_path=AUDIT_LOG, output_csv_path='input_with_urls.csv'):
    """
    Updates the input CSV with Image Source URL and Status from the audit log.
    Matches items based on SKU.
    """
    try:
        logging.info(f"Updating {output_csv_path} with image data...")
        
        if not os.path.exists(audit_log_path):
            logging.warning(f"Audit log {audit_log_path} not found. Cannot update CSV.")
            return

        if not os.path.exists(input_csv_path):
             logging.warning(f"Input CSV {input_csv_path} not found. Cannot update CSV.")
             return

        # Read Input and Log
        df = pd.read_csv(input_csv_path)
        log_df = pd.read_csv(audit_log_path)
        
        # Ensure SKU columns are strings and stripped for accurate matching
        # Check if 'SKU' exists in both
        if 'SKU' not in df.columns:
            logging.error("Input CSV missing 'SKU' column.")
            return
        if 'SKU' not in log_df.columns:
             logging.error("Audit log missing 'SKU' column.")
             return

        df['SKU'] = df['SKU'].astype(str).str.strip()
        log_df['SKU'] = log_df['SKU'].astype(str).str.strip()
        
        # Deduplicate log, keeping the LAST attempt for each SKU (most recent status)
        # We assume 'SKU' is the unique identifier. We don't really need 'Original Name' for deduping if SKU is unique.
        log_df = log_df.drop_duplicates(subset=['SKU'], keep='last')
        
        # Select relevant columns from log to merge
        # Map 'Saved Filename' and 'Image Source URL' and 'Status'
        # The log file has columns: SKU, Original Name, Similarity Score, Image Source URL, Saved Filename, Status, ...
        cols_to_merge = ['SKU', 'Image Source URL', 'Saved Filename', 'Status']
        
        # Filter log_df to only have columns that exist (just safety)
        cols_to_merge = [c for c in cols_to_merge if c in log_df.columns]
        
        # Drop existing columns in df if they pretend to be the ones we are updating, to avoid suffix issues e.g. _x _y
        for col in ['Image Source URL', 'Saved Filename', 'Status']:
            if col in df.columns:
                df = df.drop(columns=[col])

        # Merge: Left join to keep all input rows, add info where available
        merged_df = pd.merge(df, log_df[cols_to_merge], on='SKU', how='left')
        
        # Write to output file
        merged_df.to_csv(output_csv_path, index=False)
        logging.info(f"Successfully updated '{output_csv_path}'.")

    except Exception as e:
        logging.error(f"Failed to generate {output_csv_path}: {e}")

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

    # Generate enhanced CSV with URLs using the new function
    update_csv_with_urls()

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Run only first 5 items")
    args = parser.parse_args()
    main(dry_run=args.dry_run)