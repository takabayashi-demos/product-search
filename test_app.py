"""Tests for product-search service."""
import pytest
import json
from app import app


@pytest.fixture
def client():
    app.config['TESTING'] = True
    with app.test_client() as client:
        yield client


class TestSecurity:
    """Security-focused test cases."""
    
    def test_search_query_length_validation(self, client):
        """Test that overly long queries are rejected."""
        long_query = 'a' * 101
        response = client.get(f'/api/v1/search?q={long_query}')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'too long' in data['error'].lower()
    
    def test_search_sanitizes_dangerous_characters(self, client):
        """Test that dangerous characters are removed from queries."""
        malicious_query = '<script>alert("xss")</script>'
        response = client.get(f'/api/v1/search?q={malicious_query}')
        assert response.status_code == 200
        data = json.loads(response.data)
        # Dangerous characters should be stripped
        assert '<' not in data['query']
        assert '>' not in data['query']
        assert 'script' in data['query']  # Only safe text remains
    
    def test_search_rejects_invalid_limit(self, client):
        """Test that non-integer limit values are rejected."""
        response = client.get('/api/v1/search?q=laptop&limit=invalid')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'invalid' in data['error'].lower()
    
    def test_search_rejects_negative_offset(self, client):
        """Test that negative offset values are rejected."""
        response = client.get('/api/v1/search?q=laptop&offset=-1')
        assert response.status_code == 400
        data = json.loads(response.data)
        assert 'non-negative' in data['error'].lower()
    
    def test_products_rejects_invalid_parameters(self, client):
        """Test that products endpoint validates parameters."""
        response = client.get('/api/v1/products?limit=abc')
        assert response.status_code == 400
        
        response = client.get('/api/v1/products?offset=-5')
        assert response.status_code == 400
    
    def test_health_endpoint_not_rate_limited(self, client):
        """Test that health check is exempt from rate limiting."""
        # Health endpoint should always respond
        for _ in range(10):
            response = client.get('/health')
            assert response.status_code == 200


class TestFunctionality:
    """Functional test cases."""
    
    def test_search_returns_results(self, client):
        """Test that search returns matching products."""
        response = client.get('/api/v1/search?q=laptop')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['total'] > 0
        assert len(data['items']) > 0
    
    def test_search_requires_query(self, client):
        """Test that search requires q parameter."""
        response = client.get('/api/v1/search')
        assert response.status_code == 400
    
    def test_products_pagination(self, client):
        """Test that products endpoint supports pagination."""
        response = client.get('/api/v1/products?limit=2&offset=0')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert len(data['products']) == 2
        assert data['total'] == 5
