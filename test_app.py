"""Tests for QueryCache LRU eviction behavior."""
import time
from unittest.mock import patch

import pytest

from app import QueryCache


class TestQueryCacheEviction:
    """Verify the cache evicts the least-recently-used entry when full."""

    def test_evicts_oldest_entry_when_full(self):
        cache = QueryCache(max_size=3, ttl_seconds=300)

        cache.put("alpha", 10, 0, {"q": "alpha"})
        cache.put("beta", 10, 0, {"q": "beta"})
        cache.put("gamma", 10, 0, {"q": "gamma"})

        # Cache is full. Inserting a fourth entry should evict "alpha" (oldest).
        cache.put("delta", 10, 0, {"q": "delta"})

        assert cache.get("alpha", 10, 0) is None, "oldest entry should have been evicted"
        assert cache.get("beta", 10, 0) == {"q": "beta"}
        assert cache.get("gamma", 10, 0) == {"q": "gamma"}
        assert cache.get("delta", 10, 0) == {"q": "delta"}

    def test_recently_accessed_entry_survives_eviction(self):
        cache = QueryCache(max_size=3, ttl_seconds=300)

        cache.put("alpha", 10, 0, {"q": "alpha"})
        cache.put("beta", 10, 0, {"q": "beta"})
        cache.put("gamma", 10, 0, {"q": "gamma"})

        # Access "alpha" to move it to the end (most-recently-used).
        cache.get("alpha", 10, 0)

        # "beta" is now the LRU entry and should be evicted.
        cache.put("delta", 10, 0, {"q": "delta"})

        assert cache.get("alpha", 10, 0) == {"q": "alpha"}, "accessed entry should survive"
        assert cache.get("beta", 10, 0) is None, "LRU entry should have been evicted"

    def test_update_existing_key_does_not_evict(self):
        cache = QueryCache(max_size=3, ttl_seconds=300)

        cache.put("alpha", 10, 0, {"q": "alpha"})
        cache.put("beta", 10, 0, {"q": "beta"})
        cache.put("gamma", 10, 0, {"q": "gamma"})

        # Updating an existing key shouldn't trigger eviction.
        cache.put("alpha", 10, 0, {"q": "alpha_v2"})

        assert cache.get("alpha", 10, 0) == {"q": "alpha_v2"}
        assert cache.get("beta", 10, 0) == {"q": "beta"}
        assert cache.get("gamma", 10, 0) == {"q": "gamma"}

    def test_cache_never_exceeds_max_size(self):
        cache = QueryCache(max_size=5, ttl_seconds=300)

        for i in range(20):
            cache.put(f"query_{i}", 10, 0, {"i": i})

        stats = cache.stats()
        assert stats["size"] <= 5

    def test_expired_entry_not_returned(self):
        cache = QueryCache(max_size=10, ttl_seconds=1)

        cache.put("alpha", 10, 0, {"q": "alpha"})
        time.sleep(1.1)

        assert cache.get("alpha", 10, 0) is None

    def test_stats_tracks_hits_and_misses(self):
        cache = QueryCache(max_size=10, ttl_seconds=300)

        cache.put("alpha", 10, 0, {"q": "alpha"})
        cache.get("alpha", 10, 0)  # hit
        cache.get("beta", 10, 0)   # miss

        stats = cache.stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0.5
