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
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))
    min_price = request.args.get('min_price')
    max_price = request.args.get('max_price')

    if not query:
        return jsonify({'error': 'q parameter required'}), 400

    # Simple search filter
    results = [p for p in products if query in p['name'].lower() or query in p['category'].lower()]

    # Apply price range filters
    if min_price is not None:
        try:
            min_price = float(min_price)
            results = [p for p in results if p['price'] >= min_price]
        except ValueError:
            return jsonify({'error': 'min_price must be a valid number'}), 400

    if max_price is not None:
        try:
            max_price = float(max_price)
            results = [p for p in results if p['price'] <= max_price]
        except ValueError:
            return jsonify({'error': 'max_price must be a valid number'}), 400

    paginated = results[offset:offset + limit]

    return jsonify({
        'total': len(results),
        'items': paginated,
        'query': query
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

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f'Unhandled error: {e}')
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f'Starting product-search on port {port}')
    app.run(host='0.0.0.0', port=port)
