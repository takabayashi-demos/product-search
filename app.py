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
                self._cache.move_to_end(key)
                self._cache[key] = (time.monotonic(), value)
                return
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
            self._cache[key] = (time.monotonic(), value)

    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            }


PRODUCTS_INDEX = os.getenv("ES_PRODUCTS_INDEX", "products")
_cache = QueryCache(
    max_size=int(os.getenv("CACHE_MAX_SIZE", "2000")),
    ttl_seconds=int(os.getenv("CACHE_TTL_SECONDS", "30")),
)


def create_app() -> Flask:
    app = Flask(__name__)

    @app.route("/healthz")
    def healthz():
        try:
            es = ESClientManager.get_instance().client
            if es.ping():
                return jsonify({"status": "healthy"}), 200
        except Exception:
            pass
        return jsonify({"status": "unhealthy"}), 503

    @app.route("/api/v1/search")
    def search():
        q = request.args.get("q", "").strip()
        if not q:
            return jsonify({"error": "query parameter 'q' is required"}), 400

        limit = min(int(request.args.get("limit", "20")), 100)
        offset = int(request.args.get("offset", "0"))

        cached = _cache.get(q, limit, offset)
        if cached is not None:
            return jsonify(cached), 200

        es = ESClientManager.get_instance().client
        body = {
            "query": {
                "multi_match": {
                    "query": q,
                    "fields": ["name^3", "description", "category^2", "brand^2"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "from": offset,
            "size": limit,
        }
        resp = es.search(index=PRODUCTS_INDEX, body=body)
        hits = resp["hits"]
        result = {
            "total": hits["total"]["value"],
            "items": [{**h["_source"], "_score": h["_score"]} for h in hits["hits"]],
            "limit": limit,
            "offset": offset,
        }
        _cache.put(q, limit, offset, result)
        return jsonify(result), 200

    @app.route("/api/v1/cache/stats")
    def cache_stats():
        return jsonify(_cache.stats()), 200

    return app


if __name__ == "__main__":
    app = create_app()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "8080")))
