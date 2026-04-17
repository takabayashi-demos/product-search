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

def get_int_param(param_name, default, max_value=None):
    """Safely parse integer query parameter with validation."""
    value = request.args.get(param_name, str(default))
    try:
        parsed = int(value)
        if parsed < 0:
            raise ValueError(f"{param_name} must be non-negative")
        if max_value and parsed > max_value:
            return max_value
        return parsed
    except ValueError as e:
        raise ValueError(f"Invalid {param_name}: {value}") from e

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'UP', 'service': 'product-search'})

@app.route('/api/v1/search', methods=['GET'])
def search():
    query = request.args.get('q', '').lower()

    if not query:
        return jsonify({'error': 'q parameter required'}), 400

    try:
        limit = get_int_param('limit', 20, max_value=100)
        offset = get_int_param('offset', 0)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

    # Simple search filter
    results = [p for p in products if query in p['name'].lower() or query in p['category'].lower()]

    paginated = results[offset:offset + limit]

    return jsonify({
        'total': len(results),
        'items': paginated,
        'query': query
    })

@app.route('/api/v1/products', methods=['GET'])
def get_products():
    try:
        limit = get_int_param('limit', 50, max_value=200)
        offset = get_int_param('offset', 0)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

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
