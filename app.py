"""Product search microservice with Elasticsearch integration."""
import os
import time
import hashlib
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)

# Elasticsearch defaults
ES_DEFAULT_HOST = "http://localhost:9200"
ES_DEFAULT_POOL_SIZE = 10
ES_DEFAULT_POOL_MAXSIZE = 25
ES_DEFAULT_MAX_RETRIES = 3
ES_DEFAULT_TIMEOUT = 10

# Cache defaults
CACHE_DEFAULT_MAX_SIZE = 1000
CACHE_DEFAULT_TTL_SECONDS = 60

# Search defaults
SEARCH_DEFAULT_LIMIT = 20
SEARCH_MAX_LIMIT = 100
SEARCH_DEFAULT_OFFSET = 0


@dataclass
class ESPoolConfig:
    """Elasticsearch connection pool configuration."""
    hosts: List[str] = field(default_factory=lambda: [
        os.getenv("ES_HOST", ES_DEFAULT_HOST)
    ])
    pool_size: int = int(os.getenv("ES_POOL_SIZE", str(ES_DEFAULT_POOL_SIZE)))
    pool_maxsize: int = int(os.getenv("ES_POOL_MAXSIZE", str(ES_DEFAULT_POOL_MAXSIZE)))
    retry_on_timeout: bool = True
    max_retries: int = int(os.getenv("ES_MAX_RETRIES", str(ES_DEFAULT_MAX_RETRIES)))
    timeout: int = int(os.getenv("ES_TIMEOUT", str(ES_DEFAULT_TIMEOUT)))
    sniff_on_start: bool = os.getenv("ES_SNIFF_ON_START", "false").lower() == "true"


class ESClientManager:
    """Manages a pooled Elasticsearch client singleton."""

    _instance: Optional["ESClientManager"] = None
    _lock = Lock()

    def __init__(self, config: Optional[ESPoolConfig] = None):
        self._config = config or ESPoolConfig()
        self._client: Optional[Elasticsearch] = None

    @classmethod
    def get_instance(cls, config: Optional[ESPoolConfig] = None) -> "ESClientManager":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(config)
        return cls._instance

    @classmethod
    def reset(cls):
        """Reset the singleton — used in tests."""
        with cls._lock:
            if cls._instance and cls._instance._client:
                cls._instance._client.close()
            cls._instance = None

    @property
    def client(self) -> Elasticsearch:
        if self._client is None:
            with self._lock:
                if self._client is None:
                    self._client = Elasticsearch(
                        self._config.hosts,
                        maxsize=self._config.pool_maxsize,
                        retry_on_timeout=self._config.retry_on_timeout,
                        max_retries=self._config.max_retries,
                        timeout=self._config.timeout,
                        sniff_on_start=self._config.sniff_on_start,
                    )
                    logger.info(
                        "ES client initialized: pool_maxsize=%d, timeout=%ds",
                        self._config.pool_maxsize,
                        self._config.timeout,
                    )
        return self._client


class QueryCache:
    """Thread-safe LRU cache with TTL for search query results."""

    def __init__(self, max_size: int = CACHE_DEFAULT_MAX_SIZE, ttl_seconds: int = CACHE_DEFAULT_TTL_SECONDS):
        self._max_size = max_size
        self._ttl = ttl_seconds
        self._cache: OrderedDict[str, Tuple[float, dict]] = OrderedDict()
        self._lock = Lock()
        self._hits = 0
        self._misses = 0

    @staticmethod
    def _make_key(query: str, limit: int, offset: int) -> str:
        raw = f"{query.strip().lower()}:{limit}:{offset}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, query: str, limit: int, offset: int) -> Optional[dict]:
        key = self._make_key(query, limit, offset)
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                self._misses += 1
                return None
            ts, value = entry
            if time.monotonic() - ts > self._ttl:
                del self._cache[key]
                self._misses += 1
                return None
            self._cache.move_to_end(key)
            self._hits += 1
            return value

    def put(self, query: str, limit: int, offset: int, value: dict) -> None:
        key = self._make_key(query, limit, offset)
        with self._lock:
            if key in self._cache:
                del self._cache[key]
            self._cache[key] = (time.monotonic(), value)
            if len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    def stats(self) -> dict:
        """Return cache statistics."""
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0.0
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate_pct": round(hit_rate, 2),
                "ttl_seconds": self._ttl,
            }

    def clear(self) -> None:
        """Clear all cache entries and reset stats."""
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0


app = Flask(__name__)
es_manager = ESClientManager.get_instance()
query_cache = QueryCache()


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint with cache statistics."""
    try:
        es_manager.client.info()
        es_status = "up"
    except Exception as e:
        logger.error("ES health check failed: %s", str(e))
        es_status = "down"
    
    return jsonify({
        "status": "ok" if es_status == "up" else "degraded",
        "elasticsearch": es_status,
        "cache": query_cache.stats(),
    })


@app.route("/search", methods=["GET"])
def search():
    """Search products via Elasticsearch."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Missing query parameter 'q'"}), 400
    
    try:
        limit = min(int(request.args.get("limit", SEARCH_DEFAULT_LIMIT)), SEARCH_MAX_LIMIT)
        offset = int(request.args.get("offset", SEARCH_DEFAULT_OFFSET))
    except ValueError:
        return jsonify({"error": "Invalid limit or offset"}), 400
    
    cached = query_cache.get(query, limit, offset)
    if cached:
        logger.info("Cache hit for query: %s", query)
        return jsonify(cached)
    
    try:
        es_query = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "description", "category^2"],
                    "type": "best_fields",
                }
            },
            "from": offset,
            "size": limit,
        }
        
        response = es_manager.client.search(index="products", body=es_query)
        results = {
            "query": query,
            "total": response["hits"]["total"]["value"],
            "results": [
                {
                    "id": hit["_id"],
                    "score": hit["_score"],
                    **hit["_source"],
                }
                for hit in response["hits"]["hits"]
            ],
        }
        
        query_cache.put(query, limit, offset, results)
        logger.info("ES query executed: query=%s, results=%d", query, len(results["results"]))
        return jsonify(results)
    
    except Exception as e:
        logger.error("Search failed: %s", str(e), exc_info=True)
        return jsonify({"error": "Search failed"}), 500


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    app.run(host="0.0.0.0", port=8080)
