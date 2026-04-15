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
from elasticsearch import Elasticsearch, ConnectionPool, helpers

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
        return jsonify({
            "total": hits.get("total", {}).get("value", 0),
            "items": [h["_source"] for h in hits.get("hits", [])],
        })

    return app
