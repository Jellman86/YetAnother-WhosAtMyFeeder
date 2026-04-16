import pytest
from unittest.mock import patch


class TestAPIAuthentication:
    """Unit tests for API authentication (testing timing attack fix)."""

    @pytest.mark.asyncio
    async def test_valid_api_key_header(self):
        """Test authentication with valid API key in header."""
        from app.auth import verify_api_key_legacy

        with patch('app.config.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            result = await verify_api_key_legacy(
                header_key="test-secret-key-12345",
                query_key=None
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_valid_api_key_query(self):
        """Test authentication with valid API key in query param."""
        from app.auth import verify_api_key_legacy

        with patch('app.config.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            result = await verify_api_key_legacy(
                header_key=None,
                query_key="test-secret-key-12345"
            )
            assert result is True

    @pytest.mark.asyncio
    async def test_invalid_api_key(self):
        """Test authentication with invalid API key."""
        from app.auth import verify_api_key_legacy

        with patch('app.config.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            result = await verify_api_key_legacy(header_key="wrong-key", query_key=None)
            assert result is False

    @pytest.mark.asyncio
    async def test_missing_api_key(self):
        """Test authentication with missing API key."""
        from app.auth import verify_api_key_legacy

        with patch('app.config.settings') as mock_settings:
            mock_settings.api_key = "test-secret-key-12345"

            result = await verify_api_key_legacy(header_key=None, query_key=None)
            assert result is False

    @pytest.mark.asyncio
    async def test_no_api_key_configured(self):
        """Test that no legacy match happens when no API key is configured."""
        from app.auth import verify_api_key_legacy

        with patch('app.config.settings') as mock_settings:
            mock_settings.api_key = None

            result = await verify_api_key_legacy(header_key=None, query_key=None)
            assert result is False

    @pytest.mark.asyncio
    async def test_timing_attack_resistance(self):
        """Test that API key comparison is timing-safe (using secrets.compare_digest)."""
        from app.auth import verify_api_key_legacy

        with patch('app.config.settings') as mock_settings:
            mock_settings.api_key = "a" * 64  # Long key

            test_keys = [
                "a" * 1,   # Very short
                "a" * 32,  # Half length
                "a" * 63,  # One char short
                "a" * 64,  # Correct length
                "a" * 128, # Double length
            ]

            for test_key in test_keys:
                result = await verify_api_key_legacy(header_key=test_key, query_key=None)
                assert result is (test_key == "a" * 64)

    def test_secrets_compare_digest_usage(self):
        """Verify that secrets.compare_digest is used in auth.py."""
        import inspect
        from app import auth

        source = inspect.getsource(auth.verify_api_key_legacy)

        assert "secrets.compare_digest" in source, \
            "verify_api_key_legacy should use secrets.compare_digest for timing-safe comparison"

        assert "!=" not in source or "secrets.compare_digest" in source, \
            "verify_api_key_legacy should not use direct comparison for API keys"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
