"""Product search microservice with Elasticsearch integration."""
import os
import time
import hashlib
import json
import logging
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from threading import Lock
from typing import Dict, List, Optional, Tuple

from flask import Flask, jsonify, request
from elasticsearch import Elasticsearch, helpers

logger = logging.getLogger(__name__)


@dataclass
class ESPoolConfig:
    """Elasticsearch connection pool configuration."""
    hosts: List[str] = field(default_factory=lambda: [
        os.getenv("ES_HOST", "http://localhost:9200")
    ])
    pool_size: int = int(os.getenv("ES_POOL_SIZE", "10"))
    pool_maxsize: int = int(os.getenv("ES_POOL_MAXSIZE", "25"))
    retry_on_timeout: bool = True
    max_retries: int = int(os.getenv("ES_MAX_RETRIES", "3"))
    timeout: int = int(os.getenv("ES_TIMEOUT", "10"))
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

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 60):
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
            elif len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (time.monotonic(), value)

    def stats(self) -> Dict[str, int]:
        with self._lock:
            total = self._hits + self._misses
            hit_rate = (self._hits / total * 100) if total > 0 else 0
            return {
                "hits": self._hits,
                "misses": self._misses,
                "size": len(self._cache),
                "hit_rate_pct": round(hit_rate, 2),
            }


app = Flask(__name__)
es_manager = ESClientManager.get_instance()
query_cache = QueryCache(
    max_size=int(os.getenv("CACHE_SIZE", "1000")),
    ttl_seconds=int(os.getenv("CACHE_TTL", "60")),
)

MAX_BULK_QUERIES = int(os.getenv("MAX_BULK_QUERIES", "10"))
BULK_THREAD_POOL_SIZE = int(os.getenv("BULK_THREAD_POOL_SIZE", "5"))


def _execute_search(query: str, limit: int = 20, offset: int = 0) -> dict:
    """Execute a single search query with caching."""
    cached = query_cache.get(query, limit, offset)
    if cached is not None:
        return cached

    es_client = es_manager.client
    body = {
        "query": {"multi_match": {"query": query, "fields": ["name^3", "description", "category"]}},
        "from": offset,
        "size": limit,
    }
    
    response = es_client.search(index="products", body=body)
    results = {
        "total": response["hits"]["total"]["value"],
        "items": [{"id": hit["_id"], **hit["_source"]} for hit in response["hits"]["hits"]],
    }
    
    query_cache.put(query, limit, offset, results)
    return results


@app.route("/api/v1/search", methods=["GET"])
def search():
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "query parameter 'q' is required"}), 400

    limit = min(int(request.args.get("limit", 20)), 100)
    offset = int(request.args.get("offset", 0))

    try:
        results = _execute_search(query, limit, offset)
        return jsonify(results)
    except Exception as e:
        logger.error("Search failed: %s", e, exc_info=True)
        return jsonify({"error": "search failed"}), 500


@app.route("/api/v1/bulk-search", methods=["POST"])
def bulk_search():
    """Execute multiple search queries concurrently."""
    data = request.get_json()
    if not data or "queries" not in data:
        return jsonify({"error": "request body must contain 'queries' array"}), 400

    queries = data["queries"]
    if not isinstance(queries, list) or len(queries) == 0:
        return jsonify({"error": "queries must be a non-empty array"}), 400

    if len(queries) > MAX_BULK_QUERIES:
        return jsonify({"error": f"maximum {MAX_BULK_QUERIES} queries allowed"}), 400

    results = []
    with ThreadPoolExecutor(max_workers=BULK_THREAD_POOL_SIZE) as executor:
        futures = {}
        for idx, q in enumerate(queries):
            if not isinstance(q, dict) or "q" not in q:
                results.append({"index": idx, "error": "invalid query format"})
                continue
            
            query_str = q["q"].strip()
            if not query_str:
                results.append({"index": idx, "error": "query cannot be empty"})
                continue

            limit = min(int(q.get("limit", 20)), 100)
            offset = int(q.get("offset", 0))
            
            future = executor.submit(_execute_search, query_str, limit, offset)
            futures[future] = idx

        for future in as_completed(futures):
            idx = futures[future]
            try:
                result = future.result()
                results.append({"index": idx, "data": result})
            except Exception as e:
                logger.error("Bulk query %d failed: %s", idx, e)
                results.append({"index": idx, "error": str(e)})

    results.sort(key=lambda x: x["index"])
    return jsonify({"results": results})


@app.route("/health", methods=["GET"])
def health():
    try:
        es_manager.client.ping()
        return jsonify({"status": "healthy", "cache": query_cache.stats()})
    except Exception:
        return jsonify({"status": "unhealthy"}), 503


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
