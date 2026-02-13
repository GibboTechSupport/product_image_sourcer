"""
WP Product Automator
====================
Fetches products from WordPress/WooCommerce, identifies those missing images
or with "Uncategorized" category, sources images, and assigns categories.
"""

import os
import sys
import logging
import argparse
from rapidfuzz import fuzz
from fake_useragent import UserAgent

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("wp_automator.log"),
        logging.StreamHandler()
    ]
)

# Import our modules
try:
    import wordpress_api
    from image_sourcer import find_and_save_image
except ImportError as e:
    logging.error(f"Failed to import required modules: {e}")
    sys.exit(1)

OUTPUT_DIR = "product_images"

# Common category keywords for prediction
CATEGORY_KEYWORDS = {
    'dairy': ['milk', 'cheese', 'yogurt', 'cream', 'butter', 'curd', 'paneer', 'ghee'],
    'frozen': ['frozen', 'ice cream', 'popsicle', 'freezer'],
    'beverages': ['juice', 'soda', 'drink', 'water', 'tea', 'coffee', 'cola', 'energy'],
    'snacks': ['chips', 'crackers', 'cookies', 'biscuits', 'nuts', 'popcorn', 'candy'],
    'bakery': ['bread', 'cake', 'pastry', 'muffin', 'donut', 'roll', 'bun'],
    'produce': ['fruit', 'vegetable', 'fresh', 'apple', 'banana', 'tomato', 'onion', 'potato'],
    'meat': ['chicken', 'beef', 'pork', 'lamb', 'meat', 'steak', 'sausage'],
    'seafood': ['fish', 'shrimp', 'salmon', 'tuna', 'crab', 'lobster', 'seafood'],
    'grocery': ['rice', 'flour', 'oil', 'sugar', 'salt', 'spice', 'sauce', 'pasta', 'noodle'],
    'household': ['soap', 'detergent', 'cleaner', 'tissue', 'paper', 'towel'],
    'personal care': ['shampoo', 'toothpaste', 'lotion', 'deodorant'],
}


def predict_category(product_name, categories_by_name):
    """
    Predict the best category for a product based on its name.
    Returns (category_id, confidence_score) or (None, 0) if no match.
    """
    if not product_name:
        return None, 0
    
    name_lower = product_name.lower()
    
    # First: Try direct fuzzy match against existing category names
    best_cat_id = None
    best_score = 0
    
    for cat_name, cat_id in categories_by_name.items():
        score = fuzz.partial_ratio(name_lower, cat_name)
        if score > best_score and score >= 70:
            best_score = score
            best_cat_id = cat_id
    
    if best_cat_id and best_score >= 80:
        return best_cat_id, best_score
    
    # Second: Keyword-based matching
    for cat_key, keywords in CATEGORY_KEYWORDS.items():
        for keyword in keywords:
            if keyword in name_lower:
                # Find the matching category in WP
                for cat_name, cat_id in categories_by_name.items():
                    if cat_key in cat_name or fuzz.partial_ratio(cat_key, cat_name) >= 80:
                        return cat_id, 85  # Keyword match = 85% confidence
    
    # Fallback: return best fuzzy match if any
    if best_cat_id:
        return best_cat_id, best_score
    
    return None, 0


def is_uncategorized(product):
    """Check if product is uncategorized or only has 'Uncategorized' category."""
    categories = product.get('categories', [])
    if not categories:
        return True
    
    for cat in categories:
        name = cat.get('name', '').lower()
        if 'uncategorized' not in name:
            return False  # Has at least one real category
    
    return True  # All categories are "Uncategorized"


def has_no_image(product):
    """Check if product has no images."""
    images = product.get('images', [])
    return len(images) == 0


def process_product(product, categories_by_name, ua, test_mode=False):
    """
    Process a single product: source image and/or assign category.
    Returns a result dict for logging.
    """
    product_id = product.get('id')
    name = product.get('name', '')
    sku = product.get('sku', str(product_id))
    
    result = {
        'id': product_id,
        'sku': sku,
        'name': name,
        'image_status': 'Skipped',
        'category_status': 'Skipped',
        'old_categories': [c.get('name') for c in product.get('categories', [])],
        'new_category': None,
    }
    
    needs_image = has_no_image(product)
    needs_category = is_uncategorized(product)
    
    if not needs_image and not needs_category:
        result['image_status'] = 'Already Has Image'
        result['category_status'] = 'Already Categorized'
        return result
    
    logging.info(f"\n--- Processing: {name} (ID: {product_id}, SKU: {sku}) ---")
    logging.info(f"  Needs Image: {needs_image}, Needs Category: {needs_category}")
    
    # --- Image Sourcing ---
    if needs_image:
        logging.info("  Sourcing image...")
        final_result = None
        
        for update in find_and_save_image(name, sku, ua, output_dir=OUTPUT_DIR):
            if update.get('Status') in ['Success', 'Failed']:
                final_result = update
        
        if final_result and final_result.get('Status') == 'Success':
            result['image_status'] = 'Found'
            filepath = os.path.join(OUTPUT_DIR, final_result.get('file', ''))
            
            if not test_mode:
                # Upload to WordPress
                logging.info("  Uploading to WordPress...")
                media_id = wordpress_api.upload_media(
                    filepath, 
                    title=name, 
                    alt_text=name
                )
                
                if media_id:
                    # Assign to product
                    if wordpress_api.set_featured_image(product_id, media_id):
                        result['image_status'] = 'Uploaded & Assigned'
                    else:
                        result['image_status'] = 'Uploaded (Assign Failed)'
                else:
                    result['image_status'] = 'Found (Upload Failed)'
            else:
                result['image_status'] = 'Found (Test Mode)'
        else:
            result['image_status'] = 'Not Found'
    
    # --- Category Prediction ---
    if needs_category:
        logging.info("  Predicting category...")
        cat_id, confidence = predict_category(name, categories_by_name)
        
        if cat_id and confidence >= 80:
            # Get category name for logging
            for cat_name, cid in categories_by_name.items():
                if cid == cat_id:
                    result['new_category'] = cat_name.title()
                    break
            
            logging.info(f"  Predicted: {result['new_category']} ({confidence}% confidence)")
            
            if not test_mode:
                # Update product category
                update_data = {'categories': [{'id': cat_id}]}
                if wordpress_api.update_product(product_id, update_data):
                    result['category_status'] = f"Set to {result['new_category']}"
                else:
                    result['category_status'] = 'Update Failed'
            else:
                result['category_status'] = f"Would Set: {result['new_category']} ({confidence}%)"
        else:
            result['category_status'] = f'Low Confidence ({confidence}%)'
            logging.info(f"  Category confidence too low: {confidence}%")
    
    return result


def main():
    parser = argparse.ArgumentParser(description='WP Product Automator')
    parser.add_argument('--test-limit', type=int, default=10, 
                        help='Number of products to process (default: 10)')
    parser.add_argument('--apply', action='store_true',
                        help='Actually apply changes to WP (default: test mode)')
    args = parser.parse_args()
    
    test_mode = not args.apply
    limit = args.test_limit
    
    print("=" * 60)
    print(" WP Product Automator")
    print("=" * 60)
    print(f" Mode: {'TEST (no changes applied)' if test_mode else 'LIVE (changes will be applied)'}")
    print(f" Limit: {limit} products")
    print("=" * 60)
    
    # 1. Check WordPress connection
    if not wordpress_api.is_configured():
        logging.error("WordPress not configured. Check .env file.")
        return
    
    # 2. Fetch categories
    logging.info("Fetching categories from WordPress...")
    categories_by_id, categories_by_name = wordpress_api.get_categories()
    
    if not categories_by_name:
        logging.error("Failed to fetch categories. Check API access.")
        return
    
    logging.info(f"Found {len(categories_by_name)} categories")
    
    # 3. Fetch products (paginated)
    logging.info(f"Fetching up to {limit} products that need processing...")
    
    ua = UserAgent()
    products_to_process = []
    page = 1
    
    while len(products_to_process) < limit:
        products = wordpress_api.get_products(page=page, per_page=100)
        
        if not products:
            break
        
        for p in products:
            if has_no_image(p) or is_uncategorized(p):
                products_to_process.append(p)
                if len(products_to_process) >= limit:
                    break
        
        page += 1
    
    logging.info(f"Found {len(products_to_process)} products needing attention")
    
    if not products_to_process:
        print("\n No products found that need images or categories!")
        return
    
    # 4. Process products
    results = []
    for i, product in enumerate(products_to_process, 1):
        print(f"\n[{i}/{len(products_to_process)}] Processing...")
        result = process_product(product, categories_by_name, ua, test_mode=test_mode)
        results.append(result)
    
    # 5. Print summary
    print("\n" + "=" * 80)
    print(" RESULTS SUMMARY")
    print("=" * 80)
    print(f"{'ID':<8} {'SKU':<15} {'Name':<30} {'Image':<20} {'Category':<20}")
    print("-" * 80)
    
    for r in results:
        name_short = r['name'][:28] + '..' if len(r['name']) > 30 else r['name']
        print(f"{r['id']:<8} {r['sku']:<15} {name_short:<30} {r['image_status']:<20} {r['category_status']:<20}")
    
    print("=" * 80)
    
    # Stats
    img_found = sum(1 for r in results if 'Found' in r['image_status'] or 'Uploaded' in r['image_status'])
    cat_set = sum(1 for r in results if 'Set' in r['category_status'] or 'Would Set' in r['category_status'])
    
    print(f"\n Images: {img_found}/{len(results)} sourced")
    print(f" Categories: {cat_set}/{len(results)} predicted with >=80% confidence")
    
    if test_mode:
        print("\n NOTE: This was a TEST run. Use --apply to make actual changes.")


if __name__ == "__main__":
    main()
