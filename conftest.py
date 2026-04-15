"""Shared fixtures for product-search tests."""
import pytest
from unittest.mock import MagicMock, patch
from app import create_app, ESClientManager, ESPoolConfig


@pytest.fixture(autouse=True)
def reset_es_manager():
    """Reset ES singleton between tests."""
    ESClientManager.reset()
    yield
    ESClientManager.reset()


@pytest.fixture
def mock_es():
    """Provide a mocked Elasticsearch client."""
    mock = MagicMock()
    mock.search.return_value = {
        "hits": {
            "total": {"value": 0},
            "hits": [],
        }
    }
    return mock


@pytest.fixture
def client(mock_es):
    """Flask test client with mocked ES."""
    with patch.object(ESClientManager, "client", new_callable=lambda: property(lambda self: mock_es)):
        app = create_app(ESPoolConfig(hosts=["http://localhost:9200"]))
        app.config["TESTING"] = True
        with app.test_client() as c:
            yield c
