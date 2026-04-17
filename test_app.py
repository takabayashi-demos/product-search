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

def test_search_valid(client):
    response = client.get('/api/v1/search?q=laptop')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 1
    assert data['items'][0]['name'] == 'Laptop'

def test_search_missing_query(client):
    response = client.get('/api/v1/search')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'q parameter required' in data['error']

def test_search_invalid_limit(client):
    response = client.get('/api/v1/search?q=laptop&limit=abc')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Invalid limit' in data['error']

def test_search_invalid_offset(client):
    response = client.get('/api/v1/search?q=laptop&offset=xyz')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Invalid offset' in data['error']

def test_search_negative_limit(client):
    response = client.get('/api/v1/search?q=laptop&limit=-5')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'must be non-negative' in data['error']

def test_products_valid(client):
    response = client.get('/api/v1/products')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data['total'] == 5
    assert len(data['products']) == 5

def test_products_invalid_limit(client):
    response = client.get('/api/v1/products?limit=invalid')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Invalid limit' in data['error']

def test_products_invalid_offset(client):
    response = client.get('/api/v1/products?offset=bad')
    assert response.status_code == 400
    data = json.loads(response.data)
    assert 'Invalid offset' in data['error']

def test_products_with_pagination(client):
    response = client.get('/api/v1/products?limit=2&offset=1')
    assert response.status_code == 200
    data = json.loads(response.data)
    assert len(data['products']) == 2
    assert data['products'][0]['id'] == 2
