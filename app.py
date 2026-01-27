from flask import Flask, render_template, request, jsonify, Response
import pandas as pd
import os
import json
from image_sourcer import process_items

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
        file.save(filepath)
        
        try:
            if file.filename.endswith('.csv'):
                df = pd.read_csv(filepath)
            elif file.filename.endswith(('.xls', '.xlsx')):
                df = pd.read_excel(filepath)
            else:
                return jsonify({'error': 'Invalid file type'}), 400
            
            # Normalize columns
            df.columns = [c.strip() for c in df.columns]
            
            # Check for required columns (case-insensitive)
            # SKU is required, Name is optional
            col_map = {c.lower(): c for c in df.columns}
            if 'sku' not in col_map:
                return jsonify({'error': 'Missing required column: SKU'}), 400
            
            # Extract items
            items = []
            img_col = col_map.get('images') or col_map.get('image')
            for _, row in df.iterrows():
                name = str(row[col_map['name']]) if 'name' in col_map else ""
                has_image = False
                if img_col:
                    img_val = str(row[img_col]).strip()
                    if img_val and img_val.lower() != 'nan':
                        has_image = True
                
                items.append({
                    'SKU': str(row[col_map['sku']]),
                    'Name': name,
                    'HasImage': has_image
                })
                
            return jsonify({'items': items})
            
        except Exception as e:
            return jsonify({'error': str(e)}), 500

@app.route('/api/process', methods=['POST'])
def process():
    data = request.json
    items = data.get('items', [])
    output_dir = data.get('output_dir', '').strip()
    upload_to_wordpress = data.get('upload_to_wordpress', False)
    
    # Use default if empty
    if not output_dir:
        output_dir = "product_images"

    if not items:
        return jsonify({'error': 'No items to process'}), 400

    def generate():
        # Iterate over results from image_sourcer generator
        for result in process_items(items, output_dir=output_dir, upload_to_wordpress=upload_to_wordpress):
            # Send as SSE
            yield f"data: {json.dumps(result)}\n\n"
    
    return Response(generate(), mimetype='text/event-stream')

if __name__ == '__main__':
    app.run(debug=True, port=5000)
