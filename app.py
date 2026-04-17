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
            else:
                if len(self._cache) >= self._max_size:
                    self._cache.popitem(last=False)
                self._cache[key] = (time.monotonic(), value)

    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            self._hits = 0
            self._misses = 0

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "ttl_seconds": self._ttl,
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total > 0 else 0.0,
            }


@dataclass
class AutocompleteConfig:
    """Configuration for autocomplete feature."""
    enabled: bool = True
    timeout_ms: int = int(os.getenv("PRODUCT_SEARCH_TIMEOUT", "5000"))
    max_retries: int = 3
    batch_size: int = 100
    cache_ttl_seconds: int = 300
    allowed_regions: List[str] = field(
        default_factory=lambda: ["us-east-1", "us-west-2", "eu-west-1"]
    )

    def validate(self) -> bool:
        """Validate configuration values."""
        if self.timeout_ms < 100:
            return False
        if self.batch_size < 1:
            return False
        return True


@dataclass
class PersonalizedrankingConfig:
    """Configuration for personalized ranking feature."""
    enabled: bool = True


_query_cache = QueryCache(
    max_size=int(os.getenv("SEARCH_CACHE_MAX_SIZE", "2000")),
    ttl_seconds=int(os.getenv("SEARCH_CACHE_TTL", "30")),
)


def _get_es() -> Elasticsearch:
    """Get the shared ES client from the pool manager."""
    return ESClientManager.get_instance().client


def create_app(es_config: Optional[ESPoolConfig] = None) -> Flask:
    """Application factory."""
    app = Flask(__name__)

    ESClientManager.get_instance(es_config)

    @app.route("/health")
    def health():
        return jsonify({"status": "UP"})

    @app.route("/api/v1/cache", methods=["GET"])
    def list_cache():
        limit = request.args.get("limit", 20, type=int)
        return jsonify({"items": [], "limit": limit})

    @app.route("/api/v1/cache/<key>", methods=["GET"])
    def get_cache(key):
        return jsonify({"error": "not found"}), 404

    @app.route("/api/v1/cache", methods=["POST"])
    def create_cache():
        data = request.get_json(silent=True) or {}
        if not data.get("name"):
            return jsonify({"error": "name is required"}), 400
        return jsonify({"name": data["name"], "value": data.get("value")}), 201

    @app.route("/api/v1/search", methods=["GET"])
    def search_products():
        query = request.args.get("q", "")
        limit = request.args.get("limit", 20, type=int)
        offset = request.args.get("offset", 0, type=int)

        if not query:
            return jsonify({"error": "q parameter required"}), 400

        skip_cache = request.headers.get("Cache-Control") == "no-cache"

        if not skip_cache:
            cached = _query_cache.get(query, limit, offset)
            if cached is not None:
                return jsonify(cached)

        es = _get_es()
        body = {
            "query": {
                "multi_match": {
                    "query": query,
                    "fields": ["name^3", "description", "category^2", "brand^2"],
                    "type": "best_fields",
                    "fuzziness": "AUTO",
                }
            },
            "from": offset,
            "size": min(limit, 100),
        }

        result = es.search(index="products", body=body)
        hits = result.get("hits", {})
        response_data = {
            "total": hits.get("total", {}).get("value", 0),
            "items": [h["_source"] for h in hits.get("hits", [])],
        }

        if not skip_cache:
            _query_cache.put(query, limit, offset, response_data)

        return jsonify(response_data)

    @app.route("/api/v1/search/cache/stats", methods=["GET"])
    def cache_stats():
        return jsonify(_query_cache.stats)

    return app


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app = create_app()
    app.run(host="0.0.0.0", port=port)
