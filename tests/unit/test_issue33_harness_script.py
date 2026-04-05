import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
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


def test_fetch_settings_uses_authenticated_request(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def read(self):
            return b'{"audio_topic":"birdnet"}'

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["auth"] = request.headers.get("Authorization")
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(issue33, "urlopen", _fake_urlopen)

    payload = issue33._fetch_owner_settings(
        backend_url="http://example",
        token="jwt-token",
        timeout_seconds=9.0,
    )

    assert payload["audio_topic"] == "birdnet"
    assert captured["url"] == "http://example/api/settings"
    assert captured["auth"] == "Bearer jwt-token"
    assert captured["timeout"] == 9.0


def test_resolve_birdnet_topic_prefers_live_settings_when_no_explicit_topic(monkeypatch):
    args = issue33._build_arg_parser().parse_args([])
    monkeypatch.setattr(issue33, "_fetch_owner_settings", lambda **kwargs: {"audio_topic": "birdnet"})

    topic = issue33._resolve_birdnet_topic(args, auth_token="jwt-token")

    assert topic == "birdnet"


def test_resolve_birdnet_topic_preserves_explicit_topic(monkeypatch):
    args = issue33._build_arg_parser().parse_args(["--birdnet-topic", "birdnet/text"])
    monkeypatch.setattr(issue33, "_fetch_owner_settings", lambda **kwargs: {"audio_topic": "birdnet"})

    topic = issue33._resolve_birdnet_topic(args, auth_token="jwt-token")

    assert topic == "birdnet/text"


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


def test_normalize_issue33_evaluation_replaces_birdnet_delta_with_stall_window_freshness():
    start = datetime(2026, 4, 5, 6, 21, 0, tzinfo=timezone.utc)
    samples = [
        SimpleNamespace(observed_at=start, mqtt_birdnet_age_seconds=4.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=30), mqtt_birdnet_age_seconds=6.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=60), mqtt_birdnet_age_seconds=8.0),
    ]
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "BirdNET topic message growth below threshold (-9 < 10).",
        ],
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=True,
        samples=samples,
        induced_frigate_stall_at=start.isoformat(),
        birdnet_publish_stats={"published": 20, "publish_failures": 0, "connect_failures": 0},
        max_birdnet_active_age_seconds=20.0,
    )

    assert normalized["passed"] is True
    assert normalized["failure_reasons"] == []
    assert normalized["birdnet_publisher_ok"] is True
    assert normalized["birdnet_stall_window_samples"] == 3
    assert normalized["birdnet_stayed_fresh_during_stall"] is True


def test_normalize_issue33_evaluation_fails_when_birdnet_publisher_did_not_publish():
    start = datetime(2026, 4, 5, 6, 21, 0, tzinfo=timezone.utc)
    samples = [SimpleNamespace(observed_at=start, mqtt_birdnet_age_seconds=3.0)]
    evaluation = {
        "passed": True,
        "failure_reasons": [],
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=True,
        samples=samples,
        induced_frigate_stall_at=start.isoformat(),
        birdnet_publish_stats={"published": 0, "publish_failures": 1, "connect_failures": 0},
        max_birdnet_active_age_seconds=20.0,
    )

    assert normalized["passed"] is False
    assert "Synthetic BirdNET publisher did not produce healthy traffic." in normalized["failure_reasons"]


def test_normalize_issue33_evaluation_fails_when_birdnet_goes_stale_during_stall():
    start = datetime(2026, 4, 5, 6, 21, 0, tzinfo=timezone.utc)
    samples = [
        SimpleNamespace(observed_at=start, mqtt_birdnet_age_seconds=4.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=40), mqtt_birdnet_age_seconds=45.0),
    ]
    evaluation = {
        "passed": True,
        "failure_reasons": [],
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=True,
        samples=samples,
        induced_frigate_stall_at=start.isoformat(),
        birdnet_publish_stats={"published": 20, "publish_failures": 0, "connect_failures": 0},
        max_birdnet_active_age_seconds=20.0,
    )

    assert normalized["passed"] is False
    assert "BirdNET did not stay fresh during the induced Frigate stall window." in normalized["failure_reasons"]
