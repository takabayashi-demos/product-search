"""Tests for product search service."""
import pytest
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


def test_health_endpoint(client):
    """Test health check endpoint."""
    response = client.get('/health')
    assert response.status_code == 200
    data = response.get_json()
    assert data['status'] == 'UP'
    assert data['service'] == 'product-search'


def test_search_endpoint_success(client):
    """Test search with valid query."""
    response = client.get('/api/v1/search?q=laptop')
    assert response.status_code == 200
    data = response.get_json()
    assert 'items' in data
    assert 'total' in data
    assert data['query'] == 'laptop'
    assert len(data['items']) > 0


def test_search_endpoint_missing_query(client):
    """Test search without query parameter."""
    response = client.get('/api/v1/search')
    assert response.status_code == 400
    data = response.get_json()
    assert 'error' in data


def test_search_endpoint_pagination(client):
    """Test search pagination."""
    response = client.get('/api/v1/search?q=electronics&limit=2&offset=0')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['items']) <= 2


def test_get_products_endpoint(client):
    """Test products listing endpoint."""
    response = client.get('/api/v1/products')
    assert response.status_code == 200
    data = response.get_json()
    assert 'products' in data
    assert 'total' in data
    assert data['total'] > 0


def test_get_products_pagination(client):
    """Test products pagination."""
    response = client.get('/api/v1/products?limit=3&offset=1')
    assert response.status_code == 200
    data = response.get_json()
    assert len(data['products']) <= 3
