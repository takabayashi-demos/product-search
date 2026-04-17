"""Tests for product search microservice."""
import pytest
import json
from app import app

@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client

def test_health(client):
    response = client.get('/health')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['status'] == 'UP'
    assert data['service'] == 'product-search'

def test_search_basic(client):
    response = client.get('/api/v1/search?q=laptop')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 1
    assert data['items'][0]['name'] == 'Laptop'

def test_search_missing_query(client):
    response = client.get('/api/v1/search')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_search_category_filter(client):
    response = client.get('/api/v1/search?q=e&category=electronics')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 3
    for item in data['items']:
        assert item['category'] == 'Electronics'

def test_search_category_filter_case_insensitive(client):
    response = client.get('/api/v1/search?q=keyboard&category=ACCESSORIES')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 1
    assert data['items'][0]['name'] == 'Keyboard'

def test_search_sort_price_asc(client):
    response = client.get('/api/v1/search?q=e&sort=price_asc')
    assert response.status_code == 200
    data = json.loads(response.data)
    prices = [item['price'] for item in data['items']]
    assert prices == sorted(prices)

def test_search_sort_price_desc(client):
    response = client.get('/api/v1/search?q=e&sort=price_desc')
    assert response.status_code == 200
    data = json.loads(response.data)
    prices = [item['price'] for item in data['items']]
    assert prices == sorted(prices, reverse=True)

def test_search_sort_name(client):
    response = client.get('/api/v1/search?q=e&sort=name')
    assert response.status_code == 200
    data = json.loads(response.data)
    names = [item['name'] for item in data['items']]
    assert names == sorted(names)

def test_search_combined_filters(client):
    response = client.get('/api/v1/search?q=e&category=electronics&sort=price_asc')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 3
    assert all(item['category'] == 'Electronics' for item in data['items'])
    prices = [item['price'] for item in data['items']]
    assert prices == sorted(prices)

def test_get_products(client):
    response = client.get('/api/v1/products')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 5
    assert len(data['products']) == 5

def test_get_product_by_id_success(client):
    response = client.get('/api/v1/products/1')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['id'] == 1
    assert data['name'] == 'Laptop'
    assert data['category'] == 'Electronics'
    assert data['price'] == 999.99

def test_get_product_by_id_not_found(client):
    response = client.get('/api/v1/products/999')
    assert response.status_code == 404
    data = json.loads(response.data)
    assert 'error' in data
    assert data['error'] == 'Product not found'

def test_get_product_multiple_ids(client):
    for product_id in [1, 2, 3, 4, 5]:
        response = client.get(f'/api/v1/products/{product_id}')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['id'] == product_id
