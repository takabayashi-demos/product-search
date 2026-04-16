"""Tests for input validation and query sanitization."""
import pytest
from app import sanitize_query, validate_search_params, MAX_QUERY_LENGTH


class FakeArgs(dict):
    """Minimal request.args stand-in."""
    def get(self, key, default=None):
        return super().get(key, default)


class TestSanitizeQuery:
    def test_plain_text_unchanged(self):
        assert sanitize_query("blue jeans") == "blue jeans"

    def test_escapes_wildcards(self):
        result = sanitize_query("test*")
        assert result == "test\\*"

    def test_escapes_boolean_operators(self):
        result = sanitize_query("a && b || c")
        assert "\\&" in result
        assert "\\|" in result

    def test_escapes_parentheses(self):
        result = sanitize_query("(drop)")
        assert result == "\\(drop\\)"

    def test_escapes_colons(self):
        result = sanitize_query("_exists_:password")
        assert result == "_exists_\\:password"

    def test_escapes_quotes(self):
        result = sanitize_query('"exact match"')
        assert '\\"' in result

    def test_escapes_slashes(self):
        result = sanitize_query("/regex/")
        assert result == "\\/regex\\/"


class TestValidateSearchParams:
    def test_missing_query(self):
        err, params = validate_search_params(FakeArgs())
        assert err is not None
        assert params is None
        assert "Missing" in err

    def test_empty_query(self):
        err, params = validate_search_params(FakeArgs({"q": "   "}))
        assert err is not None
        assert "Missing" in err

    def test_query_too_long(self):
        err, params = validate_search_params(FakeArgs({"q": "x" * (MAX_QUERY_LENGTH + 1)}))
        assert err is not None
        assert "too long" in err

    def test_valid_defaults(self):
        err, params = validate_search_params(FakeArgs({"q": "shoes"}))
        assert err is None
        assert params["q"] == "shoes"
        assert params["limit"] == 20
        assert params["offset"] == 0

    def test_valid_custom_params(self):
        err, params = validate_search_params(FakeArgs({"q": "tv", "limit": "50", "offset": "10"}))
        assert err is None
        assert params["limit"] == 50
        assert params["offset"] == 10

    def test_limit_non_integer(self):
        err, _ = validate_search_params(FakeArgs({"q": "test", "limit": "abc"}))
        assert "integer" in err

    def test_limit_zero(self):
        err, _ = validate_search_params(FakeArgs({"q": "test", "limit": "0"}))
        assert err is not None

    def test_limit_exceeds_max(self):
        err, _ = validate_search_params(FakeArgs({"q": "test", "limit": "101"}))
        assert err is not None

    def test_negative_offset(self):
        err, _ = validate_search_params(FakeArgs({"q": "test", "offset": "-1"}))
        assert err is not None

    def test_offset_non_integer(self):
        err, _ = validate_search_params(FakeArgs({"q": "test", "offset": "foo"}))
        assert "integer" in err
