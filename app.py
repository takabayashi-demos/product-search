"""Product Search Service - Walmart Platform
Product search and recommendations with intentional latency.

INTENTIONAL ISSUES (for demo):
- Simulated slow Elasticsearch queries (latency)
- No query sanitization (vulnerability)
- N+1 query pattern in recommendations (latency)
- Unbounded result set (bug)
"""
from flask import Flask, request, jsonify
import os, time, random, logging

app = Flask(__name__)
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("product-search")

# Mock product catalog
PRODUCTS = [
    {"id": "P001", "name": "Samsung 65\" 4K Smart TV", "category": "electronics", "price": 599.99, "rating": 4.5, "reviews": 2341, "in_stock": True},
    {"id": "P002", "name": "Apple iPhone 15 Pro Max", "category": "electronics", "price": 1199.99, "rating": 4.7, "reviews": 5678, "in_stock": True},
    {"id": "P003", "name": "Sony WH-1000XM5 Headphones", "category": "electronics", "price": 349.99, "rating": 4.6, "reviews": 3210, "in_stock": True},
    {"id": "P004", "name": "KitchenAid Stand Mixer", "category": "home", "price": 429.99, "rating": 4.8, "reviews": 8900, "in_stock": True},
    {"id": "P005", "name": "Dyson V15 Detect Vacuum", "category": "home", "price": 749.99, "rating": 4.4, "reviews": 1567, "in_stock": False},
    {"id": "P006", "name": "Nintendo Switch OLED", "category": "gaming", "price": 349.99, "rating": 4.7, "reviews": 12000, "in_stock": True},
    {"id": "P007", "name": "Instant Pot Duo 7-in-1", "category": "home", "price": 89.99, "rating": 4.6, "reviews": 45000, "in_stock": True},
    {"id": "P008", "name": "Lego Star Wars UCS Set", "category": "toys", "price": 849.99, "rating": 4.9, "reviews": 890, "in_stock": True},
    {"id": "P009", "name": "Nike Air Max 270", "category": "clothing", "price": 159.99, "rating": 4.3, "reviews": 6700, "in_stock": True},
    {"id": "P010", "name": "Pampers Swaddlers Size 3", "category": "baby", "price": 34.99, "rating": 4.5, "reviews": 23000, "in_stock": True},
]

search_count = 0

@app.route("/health")
def health():
    return jsonify({"status": "UP", "service": "product-search", "version": "1.4.2"})

@app.route("/ready")
def ready():
    return jsonify({"status": "READY"})

@app.route("/api/v1/search")
def search():
    global search_count
    search_count += 1
    query = request.args.get("q", "")
    category = request.args.get("category", "")

    # ❌ VULNERABILITY: Query logged without sanitization
    logger.info(f"Search query: {query} | category: {category}")

    # ❌ LATENCY: Simulating slow Elasticsearch query
    base_latency = random.uniform(0.3, 0.8)
    if len(query) > 20:
        # Complex queries take even longer
        base_latency += random.uniform(0.5, 1.5)
    time.sleep(base_latency)

    # Simple search matching
    results = []
    for p in PRODUCTS:
        if query.lower() in p["name"].lower() or query.lower() in p["category"].lower():
            results.append(p)
        elif category and p["category"] == category:
            results.append(p)

    if not results and not query:
        # ❌ BUG: Returns ALL products when no query - unbounded result set
        results = PRODUCTS

    return jsonify({
        "query": query,
        "results": results,
        "total": len(results),
        "took_ms": int(base_latency * 1000),
    })

@app.route("/api/v1/search/suggest")
def suggest():
    query = request.args.get("q", "")

    # ❌ LATENCY: Autocomplete should be <50ms but takes 200-400ms
    time.sleep(random.uniform(0.2, 0.4))

    suggestions = [p["name"] for p in PRODUCTS if query.lower() in p["name"].lower()][:5]
    return jsonify({"suggestions": suggestions})

@app.route("/api/v1/recommendations/<product_id>")
def recommendations(product_id):
    # ❌ LATENCY: N+1 pattern - fetching each recommendation individually
    recs = []
    for p in random.sample(PRODUCTS, min(5, len(PRODUCTS))):
        # Simulate individual DB call per recommendation
        time.sleep(random.uniform(0.05, 0.15))
        recs.append(p)

    return jsonify({
        "product_id": product_id,
        "recommendations": recs,
        "algorithm": "collaborative_filtering_v2",
    })

@app.route("/metrics")
def metrics():
    return f"""# HELP search_requests_total Total search requests
# TYPE search_requests_total counter
search_requests_total {search_count}
# HELP search_service_up Service health
# TYPE search_service_up gauge
search_service_up 1
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
# Cache layer
# Fuzzy matching
# Result cap
# Faceted search
# Async recommendations
# Search analytics
# Fast autocomplete
# Personalization layer
