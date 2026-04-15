"""Tests for product-search service."""
import pytest
import time
from unittest.mock import MagicMock, patch
from app import QueryCache, ESClientManager


class TestHealth:
    """Health endpoint tests."""

    def test_health_endpoint(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.get_json()["status"] == "UP"


class TestCacheEndpoints:
    """Cache CRUD endpoint tests."""

    def test_cache_create(self, client):
        payload = {"name": "test", "value": 42}
        response = client.post("/api/v1/cache", json=payload)
        assert response.status_code in (200, 201)

    def test_cache_validation(self, client):
        response = client.post("/api/v1/cache", json={})
        assert response.status_code in (400, 422)

    def test_cache_not_found(self, client):
        response = client.get("/api/v1/cache/nonexistent")
        assert response.status_code == 404

    @pytest.mark.parametrize("limit", [1, 10, 50, 100])
    def test_cache_pagination(self, client, limit):
        response = client.get(f"/api/v1/cache?limit={limit}")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data.get("items", data.get("caches", []))) <= limit

    def test_cache_performance(self, client):
        start = time.monotonic()
        response = client.get("/api/v1/cache")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Took {elapsed:.2f}s, expected <0.5s"


class TestQueryCache:
    """Unit tests for the LRU query cache."""

    def test_cache_miss_returns_none(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        assert cache.get("laptop", 20, 0) is None

    def test_cache_hit_returns_stored_value(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        data = {"total": 5, "items": [{"name": "laptop"}]}
        cache.put("laptop", 20, 0, data)
        result = cache.get("laptop", 20, 0)
        assert result == data

    def test_cache_normalizes_query(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        data = {"total": 1, "items": []}
        cache.put("  Laptop  ", 20, 0, data)
        assert cache.get("laptop", 20, 0) == data

    def test_cache_differentiates_pagination(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        page1 = {"total": 100, "items": [{"name": "a"}]}
        page2 = {"total": 100, "items": [{"name": "b"}]}
        cache.put("shoes", 20, 0, page1)
        cache.put("shoes", 20, 20, page2)
        assert cache.get("shoes", 20, 0) == page1
        assert cache.get("shoes", 20, 20) == page2

    def test_cache_ttl_expiry(self):
        cache = QueryCache(max_size=10, ttl_seconds=0)
        cache.put("tv", 10, 0, {"total": 1, "items": []})
        time.sleep(0.01)
        assert cache.get("tv", 10, 0) is None

    def test_cache_evicts_lru_when_full(self):
        cache = QueryCache(max_size=2, ttl_seconds=60)
        cache.put("a", 10, 0, {"items": ["a"]})
        cache.put("b", 10, 0, {"items": ["b"]})
        cache.put("c", 10, 0, {"items": ["c"]})
        assert cache.get("a", 10, 0) is None
        assert cache.get("b", 10, 0) is not None
        assert cache.get("c", 10, 0) is not None

    def test_cache_stats(self):
        cache = QueryCache(max_size=10, ttl_seconds=60)
        cache.put("x", 10, 0, {"items": []})
        cache.get("x", 10, 0)
        cache.get("y", 10, 0)
        stats = cache.stats
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1
        assert stats["hit_rate"] == 0.5


class TestSearchEndpoint:
    """Integration tests for /api/v1/search."""

    def test_search_requires_query(self, client):
        response = client.get("/api/v1/search")
        assert response.status_code == 400

    def test_search_returns_results(self, client, mock_es):
        mock_es.search.return_value = {
            "hits": {
                "total": {"value": 1},
                "hits": [{"_source": {"name": "Widget", "price": 9.99}}],
            }
        }
        response = client.get("/api/v1/search?q=widget")
        assert response.status_code == 200
        data = response.get_json()
        assert data["total"] == 1
        assert len(data["items"]) == 1

    def test_search_cache_bypass(self, client, mock_es):
        mock_es.search.return_value = {
            "hits": {"total": {"value": 0}, "hits": []}
        }
        client.get("/api/v1/search?q=test")
        client.get("/api/v1/search?q=test",
                   headers={"Cache-Control": "no-cache"})
        assert mock_es.search.call_count == 2


class TestESClientManager:
    """Tests for connection pool manager."""

    def test_singleton_returns_same_instance(self):
        a = ESClientManager.get_instance()
        b = ESClientManager.get_instance()
        assert a is b

    def test_reset_clears_instance(self):
        a = ESClientManager.get_instance()
        ESClientManager.reset()
        b = ESClientManager.get_instance()
        assert a is not b
