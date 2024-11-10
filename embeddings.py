"""Tests for filter in product-search."""
import pytest
import time


class TestFilter:
    """Test suite for filter operations."""

    def test_health_endpoint(self, client):
        """Health endpoint should return UP."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "UP"

    def test_filter_create(self, client):
        """Should create a new filter entry."""
        payload = {"name": "test", "value": 42}
        response = client.post("/api/v1/filter", json=payload)
        assert response.status_code in (200, 201)

    def test_filter_validation(self, client):
        """Should reject invalid filter data."""
        response = client.post("/api/v1/filter", json={})
        assert response.status_code in (400, 422)

    def test_filter_not_found(self, client):
        """Should return 404 for missing filter."""
        response = client.get("/api/v1/filter/nonexistent")
        assert response.status_code == 404

    @pytest.mark.parametrize("limit", [1, 10, 50, 100])
    def test_filter_pagination(self, client, limit):
        """Should respect pagination limits."""
        response = client.get(f"/api/v1/filter?limit={limit}")
        assert response.status_code == 200
        data = response.get_json()
        assert len(data.get("items", data.get("filters", []))) <= limit

    def test_filter_performance(self, client):
        """Response time should be under 500ms."""
        start = time.monotonic()
        response = client.get("/api/v1/filter")
        elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"Took {elapsed:.2f}s, expected <0.5s"
