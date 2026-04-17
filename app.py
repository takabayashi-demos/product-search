"""Product search microservice."""
import os
import logging
from flask import Flask, jsonify, request

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# In-memory product data
products = [
    {"id": 1, "name": "Laptop", "category": "Electronics", "price": 999.99},
    {"id": 2, "name": "Phone", "category": "Electronics", "price": 699.99},
    {"id": 3, "name": "Headphones", "category": "Electronics", "price": 199.99},
    {"id": 4, "name": "Keyboard", "category": "Accessories", "price": 79.99},
    {"id": 5, "name": "Mouse", "category": "Accessories", "price": 49.99},
]

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'UP', 'service': 'product-search'})

@app.route('/api/v1/search', methods=['GET'])
def search():
    query = request.args.get('q', '').lower()
    category = request.args.get('category', '').lower()
    sort = request.args.get('sort', '')
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))

    if not query:
        return jsonify({'error': 'q parameter required'}), 400

    # Search filter
    results = [p for p in products if query in p['name'].lower() or query in p['category'].lower()]

    # Category filter
    if category:
        results = [p for p in results if p['category'].lower() == category]

    # Sorting
    if sort == 'price_asc':
        results.sort(key=lambda p: p['price'])
    elif sort == 'price_desc':
        results.sort(key=lambda p: p['price'], reverse=True)
    elif sort == 'name':
        results.sort(key=lambda p: p['name'].lower())

    paginated = results[offset:offset + limit]

    return jsonify({
        'total': len(results),
        'items': paginated,
        'query': query,
        'filters': {'category': category} if category else {}
    })

@app.route('/api/v1/products', methods=['GET'])
def get_products():
    limit = min(int(request.args.get('limit', 50)), 200)
    offset = int(request.args.get('offset', 0))

    paginated = products[offset:offset + limit]

    return jsonify({
        'products': paginated,
        'total': len(products)
    })

@app.route('/api/v1/products/<int:product_id>', methods=['GET'])
def get_product(product_id):
    product = next((p for p in products if p['id'] == product_id), None)
    
    if not product:
        return jsonify({'error': 'Product not found'}), 404
    
    return jsonify(product)

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f'Unhandled error: {e}')
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f'Starting product-search on port {port}')
    app.run(host='0.0.0.0', port=port)
