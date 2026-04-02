import importlib.util
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError


SCRIPT_PATH = Path("/config/workspace/YA-WAMF/scripts/run_issue33_harness.py")
spec = importlib.util.spec_from_file_location("run_issue33_harness", SCRIPT_PATH)
issue33 = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = issue33
assert spec.loader is not None
spec.loader.exec_module(issue33)


def test_build_thresholds_sets_issue33_specific_limits():
    parser = issue33._build_arg_parser()
    args = parser.parse_args(
        [
            "--min-reconnect-delta",
            "2",
            "--max-video-pending",
            "15",
            "--max-video-failure-count-delta",
            "1",
        ]
    )

    thresholds = issue33._build_thresholds(args)

    assert thresholds.min_topic_liveness_reconnects_delta == 2
    assert thresholds.allow_video_circuit_open is False
    assert thresholds.max_video_pending == 15
    assert thresholds.max_video_failure_count_delta == 1


def test_build_thresholds_defaults_to_zero_frigate_growth_requirement():
    parser = issue33._build_arg_parser()
    args = parser.parse_args([])

    thresholds = issue33._build_thresholds(args)

    assert thresholds.min_frigate_messages_delta == 0


def test_resolve_auth_token_prefers_explicit_token():
    args = issue33._build_arg_parser().parse_args(["--auth-token", "abc123"])

    token = issue33._resolve_auth_token(args)

    assert token == "abc123"


def test_resolve_auth_token_logs_in_with_username_and_password(monkeypatch):
    args = issue33._build_arg_parser().parse_args(
        [
            "--backend-url",
            "http://example",
            "--username",
            "owner",
            "--password",
            "secret123",
        ]
    )

    monkeypatch.setattr(issue33, "_login_for_owner_token", lambda **kwargs: "jwt-token")

    token = issue33._resolve_auth_token(args)

    assert token == "jwt-token"


def test_login_for_owner_token_uses_api_login_endpoint(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def read(self):
            return b'{"access_token":"jwt"}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        captured["body"] = request.data.decode("utf-8")
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(issue33, "urlopen", _fake_urlopen)

    token = issue33._login_for_owner_token(
        backend_url="http://example",
        username="owner",
        password="secret123",
        timeout_seconds=7.5,
    )

    assert token == "jwt"
    assert captured["url"] == "http://example/api/auth/login"
    assert captured["method"] == "POST"
    assert '"username": "owner"' in captured["body"]
    assert captured["timeout"] == 7.5


def test_login_for_owner_token_raises_readable_error_on_http_failure(monkeypatch):
    def _fake_urlopen(_request, timeout=None):
        raise HTTPError(
            url="http://example/api/auth/login",
            code=401,
            msg="Unauthorized",
            hdrs=None,
            fp=None,
        )

    monkeypatch.setattr(issue33, "urlopen", _fake_urlopen)

    try:
        issue33._login_for_owner_token(
            backend_url="http://example",
            username="owner",
            password="wrong",
            timeout_seconds=7.5,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "HTTP 401" in str(exc)


def test_login_for_owner_token_raises_readable_error_on_transport_failure(monkeypatch):
    def _fake_urlopen(_request, timeout=None):
        raise URLError("connection refused")

    monkeypatch.setattr(issue33, "urlopen", _fake_urlopen)

    try:
        issue33._login_for_owner_token(
            backend_url="http://example",
            username="owner",
            password="secret123",
            timeout_seconds=7.5,
        )
        assert False, "Expected ValueError"
    except ValueError as exc:
        assert "connection refused" in str(exc)


def test_should_stop_frigate_publisher_after_configured_delay():
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=29.9, stop_after_seconds=30.0) is False
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=30.0, stop_after_seconds=30.0) is True
    assert issue33._should_stop_frigate_publisher(elapsed_seconds=120.0, stop_after_seconds=0.0) is False


def test_normalize_issue33_evaluation_accepts_induced_stall_when_reconnect_occurs():
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "Frigate topic message growth below threshold (-163 < 1).",
            "Frigate stream stalled while BirdNET remained active (1 incident(s)).",
        ],
        "topic_liveness_reconnects_delta": 1,
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=True,
    )

    assert normalized["passed"] is True
    assert normalized["failure_reasons"] == []


def test_normalize_issue33_evaluation_keeps_failures_without_induced_stall():
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "Frigate stream stalled while BirdNET remained active (1 incident(s)).",
        ],
        "topic_liveness_reconnects_delta": 1,
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=False,
    )

    assert normalized["passed"] is False
    assert normalized["failure_reasons"] == [
        "Frigate stream stalled while BirdNET remained active (1 incident(s)).",
    ]
