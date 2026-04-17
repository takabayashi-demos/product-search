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
    sort_by = request.args.get('sort_by', '')
    sort_order = request.args.get('sort_order', 'asc')
    limit = min(int(request.args.get('limit', 20)), 100)
    offset = int(request.args.get('offset', 0))

    if not query:
        return jsonify({'error': 'q parameter required'}), 400

    # Simple search filter
    results = [p for p in products if query in p['name'].lower() or query in p['category'].lower()]
    
    # Apply category filter if provided
    if category:
        results = [p for p in results if category in p['category'].lower()]
    
    # Apply sorting if requested
    if sort_by in ['price', 'name']:
        reverse = sort_order == 'desc'
        results = sorted(results, key=lambda x: x[sort_by], reverse=reverse)

    paginated = results[offset:offset + limit]

    response_data = {
        'total': len(results),
        'items': paginated,
        'query': query
    }
    
    if category:
        response_data['filters'] = {'category': category}

    return jsonify(response_data)

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
