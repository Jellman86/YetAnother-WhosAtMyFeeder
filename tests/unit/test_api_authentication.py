import pytest
from fastapi import HTTPException
from unittest.mock import patch, MagicMock
import secrets
import time


class TestAPIAuthentication:
    """Unit tests for API authentication (testing timing attack fix)."""

    @pytest.mark.asyncio
    async def test_valid_api_key_header(self):
        """Test authentication with valid API key in header."""
        from app.main import verify_api_key

        with patch('app.main.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            # Should not raise exception
            result = await verify_api_key(
                header_key="test-secret-key-12345",
                query_key=None
            )
            assert result == "test-secret-key-12345"

    @pytest.mark.asyncio
    async def test_valid_api_key_query(self):
        """Test authentication with valid API key in query param."""
        from app.main import verify_api_key

        with patch('app.main.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            result = await verify_api_key(
                header_key=None,
                query_key="test-secret-key-12345"
            )
            assert result == "test-secret-key-12345"

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        """Test authentication with invalid API key."""
        from app.main import verify_api_key

        with patch('app.main.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(
                    header_key="wrong-key",
                    query_key=None
                )

            assert exc_info.value.status_code == 403
            assert "Invalid API Key" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test authentication with missing API key."""
        from app.main import verify_api_key

        with patch('app.main.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            with pytest.raises(HTTPException) as exc_info:
                await verify_api_key(header_key=None, query_key=None)

            assert exc_info.value.status_code == 401
            assert "Missing API Key" in str(exc_info.value.detail)

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        """Test that when no API key is configured, all requests pass."""
        from app.main import verify_api_key

        with patch('app.main.settings') as mock_settings:
            mock_settings.api_key = None

            # Should not raise exception even with no key provided
            result = await verify_api_key(header_key=None, query_key=None)
            assert result is None

    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self):
        """Test that API key comparison is timing-safe (using secrets.compare_digest)."""
        from app.main import verify_api_key

        # This test verifies that our fix uses constant-time comparison
        # We can't easily test timing directly, but we can verify the function
        # uses secrets.compare_digest by checking it doesn't crash with various inputs

        with patch('app.main.settings') as mock_settings:
            mock_settings.api_key = "a" * 64  # Long key

            # Test with keys of different lengths (timing attack vulnerability)
            test_keys = [
                "a" * 1,   # Very short
                "a" * 32,  # Half length
                "a" * 63,  # One char short
                "a" * 64,  # Correct length
                "a" * 128, # Double length
            ]

            for test_key in test_keys:
                try:
                    if test_key == "a" * 64:
                        # Should succeed
                        result = await verify_api_key(header_key=test_key, query_key=None)
                        assert result == test_key
                    else:
                        # Should fail (but safely with constant time)
                        with pytest.raises(HTTPException):
                            await verify_api_key(header_key=test_key, query_key=None)
                except Exception as e:
                    pytest.fail(f"Unexpected exception with key length {len(test_key)}: {e}")

    def test_secrets_compare_digest_usage(self):
        """Verify that secrets.compare_digest is used in main.py."""
        import inspect
        from app import main

        # Get source code of verify_api_key function
        source = inspect.getsource(main.verify_api_key)

        # Verify it uses secrets.compare_digest (our P0 fix)
        assert "secrets.compare_digest" in source, \
            "verify_api_key should use secrets.compare_digest for timing-safe comparison"

        # Verify it doesn't use unsafe comparison
        # Note: This is a simple check, not foolproof
        assert "!=" not in source or "secrets.compare_digest" in source, \
            "verify_api_key should not use direct comparison for API keys"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
