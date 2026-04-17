"""Tests for product-search service."""
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

def test_search_no_query(client):
    response = client.get('/api/v1/search')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_search_with_min_price(client):
    response = client.get('/api/v1/search?q=electronics&min_price=200')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 2
    for item in data['items']:
        assert item['price'] >= 200

def test_search_with_max_price(client):
    response = client.get('/api/v1/search?q=electronics&max_price=700')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 2
    for item in data['items']:
        assert item['price'] <= 700

def test_search_with_price_range(client):
    response = client.get('/api/v1/search?q=electronics&min_price=200&max_price=800')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 2
    for item in data['items']:
        assert 200 <= item['price'] <= 800

def test_search_invalid_min_price(client):
    response = client.get('/api/v1/search?q=laptop&min_price=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_search_invalid_max_price(client):
    response = client.get('/api/v1/search?q=laptop&max_price=abc')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'error' in data

def test_get_products(client):
    response = client.get('/api/v1/products')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 5
    assert len(data['products']) == 5
