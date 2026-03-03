"""Tests for HTTPS warning context classification."""

from app.main import _classify_https_warning_reason


def test_classify_direct_http_request_without_forwarded_headers() -> None:
    reason = _classify_https_warning_reason(
        request_scheme="http",
        client_host="198.51.100.20",
        forwarded_proto=None,
        trusted_proxy_hosts=["172.19.0.15"],
    )

    assert reason == "direct_http_request"


def test_classify_untrusted_forwarded_proto_header() -> None:
    reason = _classify_https_warning_reason(
        request_scheme="http",
        client_host="198.51.100.20",
        forwarded_proto="http",
        trusted_proxy_hosts=["172.19.0.15"],
    )

    assert reason == "untrusted_forwarded_proto_ignored"


def test_classify_trusted_proxy_forwarded_http() -> None:
    reason = _classify_https_warning_reason(
        request_scheme="http",
        client_host="172.19.0.15",
        forwarded_proto="http",
        trusted_proxy_hosts=["172.19.0.15"],
    )

    assert reason == "trusted_proxy_forwarded_non_https"
