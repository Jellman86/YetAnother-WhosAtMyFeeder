"""Tests for HTTPS warning context classification."""

from app.main import (
    _classify_https_warning_reason,
    _is_internal_client_host,
    _should_warn_auth_over_http,
)


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


def test_internal_client_host_detects_loopback_and_private_ranges() -> None:
    assert _is_internal_client_host("127.0.0.1") is True
    assert _is_internal_client_host("::1") is True
    assert _is_internal_client_host("172.18.0.1") is True  # Docker bridge gateway
    assert _is_internal_client_host("10.1.2.3") is True
    assert _is_internal_client_host("192.168.1.50") is True
    assert _is_internal_client_host("169.254.1.1") is True  # link-local


def test_internal_client_host_treats_public_or_unknown_as_external() -> None:
    assert _is_internal_client_host("8.8.8.8") is False
    assert _is_internal_client_host("1.1.1.1") is False
    assert _is_internal_client_host(None) is False
    assert _is_internal_client_host("not-an-ip") is False


def test_should_not_warn_for_internal_client_treated_as_direct_http() -> None:
    # The monolith's bundled nginx / other Docker-network containers polling the API
    # over internal HTTP must not raise a credential-exposure alarm.
    assert (
        _should_warn_auth_over_http(
            warning_reason="untrusted_forwarded_proto_ignored",
            client_host="172.18.0.1",
        )
        is False
    )
    assert (
        _should_warn_auth_over_http(
            warning_reason="direct_http_request",
            client_host="127.0.0.1",
        )
        is False
    )


def test_should_warn_for_public_client_over_http() -> None:
    assert (
        _should_warn_auth_over_http(
            warning_reason="untrusted_forwarded_proto_ignored",
            client_host="8.8.8.8",
        )
        is True
    )
    assert (
        _should_warn_auth_over_http(
            warning_reason="direct_http_request",
            client_host="1.1.1.1",
        )
        is True
    )


def test_should_warn_when_trusted_proxy_reports_plaintext_user_leg() -> None:
    # A trusted proxy forwarding a non-HTTPS scheme reflects a real client leg over
    # plaintext, so it still warns even though the proxy itself is on a private address.
    assert (
        _should_warn_auth_over_http(
            warning_reason="trusted_proxy_forwarded_non_https",
            client_host="172.18.0.5",
        )
        is True
    )


def test_should_not_warn_for_secure_request() -> None:
    assert _should_warn_auth_over_http(warning_reason="secure_request", client_host="8.8.8.8") is False
