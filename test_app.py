"""Tests for product-search microservice."""
import json
import pytest
from unittest.mock import Mock, patch
from app import app, ESClientManager, query_cache


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client
    ESClientManager.reset()


@pytest.fixture
def mock_es():
    with patch("app.ESClientManager.get_instance") as mock:
        es_client = Mock()
        manager = Mock()
        manager.client = es_client
        mock.return_value = manager
        yield es_client


def test_bulk_search_success(client, mock_es):
    mock_es.search.return_value = {
        "hits": {
            "total": {"value": 2},
            "hits": [
                {"_id": "1", "_source": {"name": "Product 1", "price": 9.99}},
                {"_id": "2", "_source": {"name": "Product 2", "price": 19.99}},
            ],
        }
    }

    response = client.post(
        "/api/v1/bulk-search",
        data=json.dumps({
            "queries": [
                {"q": "laptop", "limit": 5},
                {"q": "phone", "limit": 10},
            ]
        }),
        content_type="application/json",
    )

    assert response.status_code == 200
    data = json.loads(response.data)
    assert "results" in data
    assert len(data["results"]) == 2
    assert all("index" in r for r in data["results"])
    assert all("data" in r or "error" in r for r in data["results"])


def test_bulk_search_empty_queries(client):
    response = client.post(
        "/api/v1/bulk-search",
        data=json.dumps({"queries": []}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert b"non-empty array" in response.data


def test_bulk_search_missing_queries(client):
    response = client.post(
        "/api/v1/bulk-search",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert b"must contain 'queries'" in response.data


def test_bulk_search_exceeds_max(client):
    response = client.post(
        "/api/v1/bulk-search",
        data=json.dumps({"queries": [{"q": f"query{i}"} for i in range(20)]}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert b"maximum" in response.data


def test_bulk_search_invalid_query_format(client, mock_es):
    response = client.post(
        "/api/v1/bulk-search",
        data=json.dumps({"queries": ["invalid", {"q": "valid"}]}),
        content_type="application/json",
    )
    assert response.status_code == 200
    data = json.loads(response.data)
    assert data["results"][0]["error"] == "invalid query format"


def test_bulk_search_uses_cache(client, mock_es):
    mock_es.search.return_value = {
        "hits": {"total": {"value": 1}, "hits": [{"_id": "1", "_source": {"name": "Test"}}]}
    }

    client.post(
        "/api/v1/bulk-search",
        data=json.dumps({"queries": [{"q": "laptop"}]}),
        content_type="application/json",
    )
    first_call_count = mock_es.search.call_count

    client.post(
        "/api/v1/bulk-search",
        data=json.dumps({"queries": [{"q": "laptop"}]}),
        content_type="application/json",
    )
    assert mock_es.search.call_count == first_call_count


def test_single_search_endpoint(client, mock_es):
    mock_es.search.return_value = {
        "hits": {"total": {"value": 1}, "hits": [{"_id": "1", "_source": {"name": "Test"}}]}
    }

    response = client.get("/api/v1/search?q=laptop&limit=10")
    assert response.status_code == 200
    data = json.loads(response.data)
    assert "items" in data
    assert data["total"] == 1
