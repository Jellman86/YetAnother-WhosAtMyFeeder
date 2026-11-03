from starlette.requests import Request

from app.config import settings
from app.ratelimit import _hls_limit_for_key, _hls_rate_limit_key


def _request(path: str = "/api/frigate/e1/hls/seg-1-v1-a1.m4s") -> Request:
    return Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("test", 80),
            "root_path": "",
        }
    )


def test_hls_has_an_independent_rate_limit_bucket():
    original = settings.auth.enabled
    settings.auth.enabled = True
    try:
        assert _hls_rate_limit_key(_request()) == "hls:guest:127.0.0.1"
    finally:
        settings.auth.enabled = original


def test_hls_guest_budget_accounts_for_multiple_assets_per_playback():
    original = settings.public_access.rate_limit_per_minute
    settings.public_access.rate_limit_per_minute = 30
    try:
        assert _hls_limit_for_key("hls:guest:127.0.0.1") == "300/minute"
        assert _hls_limit_for_key("hls:owner:127.0.0.1") == "1000/minute"
    finally:
        settings.public_access.rate_limit_per_minute = original
