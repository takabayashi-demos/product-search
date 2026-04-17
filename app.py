"""Product search microservice."""
import os
import logging
import re
from flask import Flask, jsonify, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# Rate limiting configuration
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["100 per minute"],
    storage_uri="memory://"
)

# In-memory product data
products = [
    {"id": 1, "name": "Laptop", "category": "Electronics", "price": 999.99},
    {"id": 2, "name": "Phone", "category": "Electronics", "price": 699.99},
    {"id": 3, "name": "Headphones", "category": "Electronics", "price": 199.99},
    {"id": 4, "name": "Keyboard", "category": "Accessories", "price": 79.99},
    {"id": 5, "name": "Mouse", "category": "Accessories", "price": 49.99},
]

@app.route('/health', methods=['GET'])
@limiter.exempt
def health():
    return jsonify({'status': 'UP', 'service': 'product-search'})

@app.route('/api/v1/search', methods=['GET'])
@limiter.limit("50 per minute")
def search():
    query = request.args.get('q', '').strip()
    
    if not query:
        return jsonify({'error': 'q parameter required'}), 400
    
    # Validate and sanitize query
    if len(query) > 100:
        return jsonify({'error': 'Query too long (max 100 characters)'}), 400
    
    # Remove potentially dangerous characters
    sanitized_query = re.sub(r'[<>"\';]', '', query).lower()
    
    try:
        limit = min(int(request.args.get('limit', 20)), 100)
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid limit or offset parameter'}), 400
    
    if offset < 0 or limit < 0:
        return jsonify({'error': 'Limit and offset must be non-negative'}), 400

    # Simple search filter
    results = [p for p in products if sanitized_query in p['name'].lower() or sanitized_query in p['category'].lower()]

    paginated = results[offset:offset + limit]

    return jsonify({
        'total': len(results),
        'items': paginated,
        'query': sanitized_query
    })

@app.route('/api/v1/products', methods=['GET'])
@limiter.limit("50 per minute")
def get_products():
    try:
        limit = min(int(request.args.get('limit', 50)), 200)
        offset = int(request.args.get('offset', 0))
    except (ValueError, TypeError):
        return jsonify({'error': 'Invalid limit or offset parameter'}), 400
    
    if offset < 0 or limit < 0:
        return jsonify({'error': 'Limit and offset must be non-negative'}), 400

    paginated = products[offset:offset + limit]

    return jsonify({
        'products': paginated,
        'total': len(products)
    })

@app.errorhandler(429)
def ratelimit_handler(e):
    logger.warning(f'Rate limit exceeded: {get_remote_address()}')
    return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429

@app.errorhandler(Exception)
def handle_error(e):
    logger.error(f'Unhandled error: {e}')
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    logger.info(f'Starting product-search on port {port}')
    app.run(host='0.0.0.0', port=port)
