"""Tests for product-search microservice."""
import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health(client):
    """Test health endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'UP'
    assert data['service'] == 'product-search'


def test_search_valid_query(client):
    """Test search with valid query."""
    response = client.get('/api/v1/search?q=laptop')
    assert response.status_code == 200
    data = response.get_json()
    assert 'items' in data
    assert data['total'] == 1
    assert data['items'][0]['name'] == 'Laptop'


def test_search_missing_query(client):
    """Test search without query parameter."""
    response = client.get('/api/v1/search')
    assert response.status_code == 400
    data = response.get_json()
    assert 'error' in data


def test_search_rate_limiting(client):
    """Test rate limiting on search endpoint."""
    # Make requests up to the limit
    for i in range(30):
        response = client.get('/api/v1/search?q=test')
        assert response.status_code == 200
    
    # Next request should be rate limited
    response = client.get('/api/v1/search?q=test')
    assert response.status_code == 429


def test_get_products(client):
    """Test get products endpoint."""
    response = client.get('/api/v1/products')
    assert response.status_code == 200
    data = response.get_json()
    assert 'products' in data
    assert data['total'] == 5


def test_get_products_with_pagination(client):
    """Test products endpoint with pagination."""
    response = client.get('/api/v1/products?limit=2&offset=1')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['products']) == 2
    assert data['products'][0]['id'] == 2
