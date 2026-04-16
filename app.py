"""Product search microservice with Elasticsearch integration."""
import os
import re
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

MAX_QUERY_LENGTH = int(os.getenv("MAX_QUERY_LENGTH", "200"))
MAX_LIMIT = 100
DEFAULT_LIMIT = 20
RATE_LIMIT_RPM = int(os.getenv("RATE_LIMIT_RPM", "60"))
RATE_LIMIT_WINDOW = 60  # seconds

# Characters that have special meaning in Elasticsearch query_string syntax.
# They must be escaped with a backslash before being passed into a query.
_ES_RESERVED_RE = re.compile(r'([+\-=&|><!(){}\[\]^"~*?:\\/])')


def sanitize_query(raw: str) -> str:
    """Escape Elasticsearch reserved characters in user input."""
    return _ES_RESERVED_RE.sub(r"\\\1", raw)


def validate_search_params(args) -> Tuple[Optional[str], Optional[dict]]:
    """Validate and parse search parameters.

    Returns (error_message, parsed_params).  Exactly one will be None.
    """
    q = args.get("q", "").strip()
    if not q:
        return "Missing required parameter: q", None
    if len(q) > MAX_QUERY_LENGTH:
        return f"Query too long (max {MAX_QUERY_LENGTH} characters)", None

    try:
        limit = int(args.get("limit", DEFAULT_LIMIT))
    except (ValueError, TypeError):
        return "Parameter 'limit' must be an integer", None
    if limit < 1 or limit > MAX_LIMIT:
        return f"Parameter 'limit' must be between 1 and {MAX_LIMIT}", None

    try:
        offset = int(args.get("offset", 0))
    except (ValueError, TypeError):
        return "Parameter 'offset' must be an integer", None
    if offset < 0:
        return "Parameter 'offset' must be >= 0", None

    return None, {"q": q, "limit": limit, "offset": offset}


class RateLimiter:
    """Sliding-window rate limiter keyed by client IP."""

    def __init__(self, max_requests: int = RATE_LIMIT_RPM, window: int = RATE_LIMIT_WINDOW):
        self._max_requests = max_requests
        self._window = window
        self._requests: Dict[str, List[float]] = {}
        self._lock = Lock()

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """Check if a request is allowed.

        Returns (allowed, retry_after_seconds).
        """
        now = time.monotonic()
        cutoff = now - self._window
        with self._lock:
            timestamps = self._requests.get(key, [])
            # Prune expired entries
            timestamps = [t for t in timestamps if t > cutoff]
            if len(timestamps) >= self._max_requests:
                oldest = timestamps[0]
                retry_after = int(oldest + self._window - now) + 1
                self._requests[key] = timestamps
                return False, retry_after
            timestamps.append(now)
            self._requests[key] = timestamps
            return True, 0

    def reset(self):
        with self._lock:
            self._requests.clear()


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
            while len(self._cache) > self._max_size:
                self._cache.popitem(last=False)

    @property
    def stats(self) -> dict:
        with self._lock:
            total = self._hits + self._misses
            return {
                "size": len(self._cache),
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": round(self._hits / total, 4) if total else 0.0,
            }


INDEX_NAME = os.getenv("ES_INDEX", "products")

cache = QueryCache(
    max_size=int(os.getenv("CACHE_MAX_SIZE", "1000")),
    ttl_seconds=int(os.getenv("CACHE_TTL", "60")),
)

rate_limiter = RateLimiter()

app = Flask(__name__)


def _get_client_ip() -> str:
    """Extract client IP, respecting X-Forwarded-For behind a trusted proxy."""
    forwarded = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _build_es_query(query: str, limit: int, offset: int) -> dict:
    safe_query = sanitize_query(query)
    return {
        "size": limit,
        "from": offset,
        "query": {
            "multi_match": {
                "query": safe_query,
                "fields": ["name^3", "description", "category^2", "brand^2"],
                "type": "best_fields",
                "fuzziness": "AUTO",
            }
        },
        "highlight": {
            "fields": {"name": {}, "description": {}},
            "pre_tags": ["<em>"],
            "post_tags": ["</em>"],
        },
    }


def _parse_hits(response: dict) -> List[dict]:
    results = []
    for hit in response.get("hits", {}).get("hits", []):
        item = hit["_source"]
        item["_score"] = hit["_score"]
        item["_id"] = hit["_id"]
        if "highlight" in hit:
            item["_highlight"] = hit["highlight"]
        results.append(item)
    return results


@app.route("/search")
def search():
    client_ip = _get_client_ip()
    allowed, retry_after = rate_limiter.is_allowed(client_ip)
    if not allowed:
        resp = jsonify({"error": "Rate limit exceeded", "retry_after": retry_after})
        resp.status_code = 429
        resp.headers["Retry-After"] = str(retry_after)
        return resp

    error, params = validate_search_params(request.args)
    if error:
        return jsonify({"error": error}), 400

    q = params["q"]
    limit = params["limit"]
    offset = params["offset"]

    cached = cache.get(q, limit, offset)
    if cached is not None:
        return jsonify(cached)

    es = ESClientManager.get_instance().client
    body = _build_es_query(q, limit, offset)
    raw = es.search(index=INDEX_NAME, body=body)

    total = raw["hits"]["total"]["value"]
    results = _parse_hits(raw)

    payload = {
        "query": q,
        "total": total,
        "limit": limit,
        "offset": offset,
        "results": results,
    }
    cache.put(q, limit, offset, payload)
    return jsonify(payload)


@app.route("/health")
def health():
    es = ESClientManager.get_instance().client
    if es.ping():
        return jsonify({"status": "healthy", "cache": cache.stats})
    return jsonify({"status": "unhealthy"}), 503


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
