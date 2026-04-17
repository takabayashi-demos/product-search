"""Tests for product-search service."""
import pytest
import time
from app import QueryCache


class TestQueryCache:
    """Test suite for QueryCache LRU behavior."""

    def test_query_cache_basic_operations(self):
        cache = QueryCache(max_size=3, ttl_seconds=60)
        
        result = cache.get("laptop", 10, 0)
        assert result is None
        
        cache.put("laptop", 10, 0, {"results": ["item1"]})
        result = cache.get("laptop", 10, 0)
        assert result == {"results": ["item1"]}
        
        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["size"] == 1

    def test_query_cache_eviction_at_max_size(self):
        cache = QueryCache(max_size=3, ttl_seconds=60)
        
        cache.put("query1", 10, 0, {"result": 1})
        cache.put("query2", 10, 0, {"result": 2})
        cache.put("query3", 10, 0, {"result": 3})
        
        stats = cache.stats()
        assert stats["size"] == 3
        assert stats["evictions"] == 0
        
        cache.put("query4", 10, 0, {"result": 4})
        
        stats = cache.stats()
        assert stats["size"] == 3
        assert stats["evictions"] == 1
        
        assert cache.get("query1", 10, 0) is None
        assert cache.get("query2", 10, 0) == {"result": 2}
        assert cache.get("query3", 10, 0) == {"result": 3}
        assert cache.get("query4", 10, 0) == {"result": 4}

    def test_query_cache_lru_ordering(self):
        cache = QueryCache(max_size=3, ttl_seconds=60)
        
        cache.put("query1", 10, 0, {"result": 1})
        cache.put("query2", 10, 0, {"result": 2})
        cache.put("query3", 10, 0, {"result": 3})
        
        cache.get("query1", 10, 0)
        
        cache.put("query4", 10, 0, {"result": 4})
        
        assert cache.get("query1", 10, 0) == {"result": 1}
        assert cache.get("query2", 10, 0) is None
        assert cache.get("query3", 10, 0) == {"result": 3}
        assert cache.get("query4", 10, 0) == {"result": 4}

    def test_query_cache_ttl_expiration(self):
        cache = QueryCache(max_size=10, ttl_seconds=1)
        
        cache.put("query1", 10, 0, {"result": 1})
        assert cache.get("query1", 10, 0) == {"result": 1}
        
        time.sleep(1.1)
        
        assert cache.get("query1", 10, 0) is None
        stats = cache.stats()
        assert stats["misses"] == 1

    def test_query_cache_update_existing_key(self):
        cache = QueryCache(max_size=3, ttl_seconds=60)
        
        cache.put("query1", 10, 0, {"result": 1})
        cache.put("query2", 10, 0, {"result": 2})
        
        cache.put("query1", 10, 0, {"result": "updated"})
        
        stats = cache.stats()
        assert stats["size"] == 2
        assert stats["evictions"] == 0
        
        result = cache.get("query1", 10, 0)
        assert result == {"result": "updated"}
