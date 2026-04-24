import importlib.util
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError


SCRIPT_PATH = Path(__file__).resolve().parents[2] / "scripts" / "run_issue33_harness.py"
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


def test_build_arg_parser_accepts_dual_track_scenarios():
    parser = issue33._build_arg_parser()

    args = parser.parse_args(["--scenario", "combined"])

    assert args.scenario == "combined"


def test_build_arg_parser_accepts_issue33_live_stress_profile():
    parser = issue33._build_arg_parser()

    args = parser.parse_args(["--stress-profile", "issue33-live"])

    assert args.stress_profile == "issue33-live"


def test_build_arg_parser_accepts_issue33_stall_probe_stress_profile():
    parser = issue33._build_arg_parser()

    args = parser.parse_args(["--stress-profile", "issue33-stall-probe"])

    assert args.stress_profile == "issue33-stall-probe"


def test_apply_stress_profile_uses_aggressive_issue33_live_defaults():
    parser = issue33._build_arg_parser()
    args = parser.parse_args(["--stress-profile", "issue33-live"])

    issue33._apply_stress_profile(args, parser=parser)

    assert args.poll_interval_seconds == 2.0
    assert args.trigger_analysis_interval_seconds == 15.0
    assert args.analysis_trigger_burst_count == 4
    assert args.analysis_trigger_burst_spacing_seconds == 0.75
    assert args.induce_frigate_stall_after_seconds == 120.0
    assert args.frigate_stall_duration_seconds == 420.0
    assert args.frigate_load_source == "replay"
    assert args.frigate_event_type == "new"
    assert args.frigate_publish_interval_seconds == 0.2
    assert args.birdnet_publish_interval_seconds == 0.25
    assert args.frigate_publisher_replicas == 4
    assert args.birdnet_publisher_replicas == 3
    assert args.max_pressure_level == "critical"


def test_apply_stress_profile_uses_lower_pressure_issue33_stall_probe_defaults():
    parser = issue33._build_arg_parser()
    args = parser.parse_args(["--stress-profile", "issue33-stall-probe"])

    issue33._apply_stress_profile(args, parser=parser)

    assert args.duration_seconds == 900
    assert args.poll_interval_seconds == 2.0
    assert args.trigger_analysis_interval_seconds == 0.0
    assert args.analysis_trigger_burst_count == 1
    assert args.induce_frigate_stall_after_seconds == 90.0
    assert args.frigate_stall_duration_seconds == 420.0
    assert args.frigate_load_source == "replay"
    assert args.frigate_event_type == "new"
    assert args.frigate_publish_interval_seconds == 0.75
    assert args.birdnet_publish_interval_seconds == 0.5
    assert args.frigate_publisher_replicas == 1
    assert args.birdnet_publisher_replicas == 1
    assert args.max_pressure_level == "high"
    assert args.max_degraded_ratio == 0.35
    assert args.min_samples == 45


def test_apply_stress_profile_preserves_explicit_overrides():
    parser = issue33._build_arg_parser()
    args = parser.parse_args(
        [
            "--stress-profile",
            "issue33-live",
            "--poll-interval-seconds",
            "1.0",
            "--analysis-trigger-burst-count",
            "6",
            "--frigate-publisher-replicas",
            "2",
            "--max-degraded-ratio",
            "0.3",
        ]
    )

    issue33._apply_stress_profile(args, parser=parser)

    assert args.poll_interval_seconds == 1.0
    assert args.analysis_trigger_burst_count == 6
    assert args.frigate_publisher_replicas == 2
    assert args.max_degraded_ratio == 0.3


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


def test_fetch_diagnostics_workspace_uses_authenticated_request(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def read(self):
            return b'{"focused_diagnostics":{"video_classifier":{"likely_last_error":"video_timeout"}}}'

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

    payload = issue33._fetch_diagnostics_workspace(
        backend_url="http://example",
        token="jwt-token",
        timeout_seconds=9.0,
    )

    assert payload["focused_diagnostics"]["video_classifier"]["likely_last_error"] == "video_timeout"
    assert captured["url"] == "http://example/api/diagnostics/workspace"
    assert captured["auth"] == "Bearer jwt-token"
    assert captured["timeout"] == 9.0


def test_fetch_diagnostics_workspace_defaults_to_api_route(monkeypatch):
    captured: dict = {}

    class _FakeResponse:
        def read(self):
            return b"{}"

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def _fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _FakeResponse()

    monkeypatch.setattr(issue33, "urlopen", _fake_urlopen)

    issue33._fetch_diagnostics_workspace(
        backend_url="http://example",
        token="jwt-token",
        timeout_seconds=3.0,
    )

    assert captured["url"] == "http://example/api/diagnostics/workspace"
    assert captured["timeout"] == 3.0


def test_resolve_birdnet_topic_prefers_live_settings_when_no_explicit_topic(monkeypatch):
    args = issue33._build_arg_parser().parse_args([])
    monkeypatch.setattr(issue33, "_fetch_owner_settings", lambda **kwargs: {"audio_topic": "birdnet"})

    topic = issue33._resolve_birdnet_topic(args, auth_token="jwt-token")

    assert topic == "birdnet"


def test_resolve_frigate_camera_prefers_live_settings_when_no_explicit_camera(monkeypatch):
    args = issue33._build_arg_parser().parse_args([])
    monkeypatch.setattr(issue33, "_fetch_owner_settings", lambda **kwargs: {"cameras": ["BirdCam", "BackYard"]})

    camera = issue33._resolve_frigate_camera(args, auth_token="jwt-token")

    assert camera == "BirdCam"


def test_resolve_frigate_camera_preserves_explicit_camera(monkeypatch):
    args = issue33._build_arg_parser().parse_args(["--frigate-camera", "SideCam"])
    monkeypatch.setattr(issue33, "_fetch_owner_settings", lambda **kwargs: {"cameras": ["BirdCam"]})

    camera = issue33._resolve_frigate_camera(args, auth_token="jwt-token")

    assert camera == "SideCam"


def test_resolve_frigate_api_url_prefers_live_settings_when_no_explicit_url(monkeypatch):
    args = issue33._build_arg_parser().parse_args([])
    monkeypatch.setattr(issue33, "_fetch_owner_settings", lambda **kwargs: {"frigate_url": "http://frigate:5000"})

    url = issue33._resolve_frigate_api_url(args, auth_token="jwt-token")

    assert url == "http://frigate:5000"


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


def test_should_pause_frigate_publisher_only_within_stall_window():
    assert issue33._should_pause_frigate_publisher(
        elapsed_seconds=29.9,
        stop_after_seconds=30.0,
        stall_duration_seconds=420.0,
    ) is False
    assert issue33._should_pause_frigate_publisher(
        elapsed_seconds=30.0,
        stop_after_seconds=30.0,
        stall_duration_seconds=420.0,
    ) is True
    assert issue33._should_pause_frigate_publisher(
        elapsed_seconds=449.9,
        stop_after_seconds=30.0,
        stall_duration_seconds=420.0,
    ) is True
    assert issue33._should_pause_frigate_publisher(
        elapsed_seconds=450.0,
        stop_after_seconds=30.0,
        stall_duration_seconds=420.0,
    ) is False


def test_should_pause_frigate_publisher_forever_when_duration_is_non_positive():
    assert issue33._should_pause_frigate_publisher(
        elapsed_seconds=120.0,
        stop_after_seconds=30.0,
        stall_duration_seconds=0.0,
    ) is True


class _FakeThread:
    def __init__(self, alive=True):
        self._alive = alive
        self.join_calls = []

    def is_alive(self):
        return self._alive

    def join(self, timeout=None):
        self.join_calls.append(timeout)
        self._alive = False


def test_set_frigate_publishers_running_stops_and_joins_threads():
    stop_event = issue33.threading.Event()
    threads = [_FakeThread(), _FakeThread()]
    started = []

    updated_threads, updated_stop_event, changed = issue33._set_frigate_publishers_running(
        should_run=False,
        threads=threads,
        stop_event=stop_event,
        start_publishers=lambda _stop_event: started.append(_stop_event) or [],
    )

    assert changed is True
    assert updated_threads == []
    assert updated_stop_event is stop_event
    assert stop_event.is_set() is True
    assert started == []
    assert threads[0].join_calls == [1.0]
    assert threads[1].join_calls == [1.0]


def test_set_frigate_publishers_running_restarts_when_threads_are_not_alive():
    stop_event = issue33.threading.Event()
    dead_thread = _FakeThread(alive=False)
    replacement_threads = [_FakeThread()]
    started_events = []

    updated_threads, updated_stop_event, changed = issue33._set_frigate_publishers_running(
        should_run=True,
        threads=[dead_thread],
        stop_event=stop_event,
        start_publishers=lambda new_stop_event: started_events.append(new_stop_event) or replacement_threads,
    )

    assert changed is True
    assert updated_threads == replacement_threads
    assert updated_stop_event is started_events[0]
    assert updated_stop_event is not stop_event


def test_set_frigate_publishers_running_keeps_existing_threads_when_already_running():
    stop_event = issue33.threading.Event()
    live_thread = _FakeThread(alive=True)
    started = []

    updated_threads, updated_stop_event, changed = issue33._set_frigate_publishers_running(
        should_run=True,
        threads=[live_thread],
        stop_event=stop_event,
        start_publishers=lambda _stop_event: started.append(_stop_event) or [_FakeThread()],
    )

    assert changed is False
    assert updated_threads == [live_thread]
    assert updated_stop_event is stop_event
    assert started == []


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


def test_normalize_issue33_evaluation_accepts_induced_stall_when_frigate_recovers_without_reconnect():
    start = datetime(2026, 4, 5, 6, 21, 0, tzinfo=timezone.utc)
    resume = start + timedelta(seconds=180)
    samples = [
        SimpleNamespace(
            observed_at=start,
            mqtt_frigate_age_seconds=0.3,
            mqtt_frigate_count=100,
            mqtt_birdnet_age_seconds=0.4,
        ),
        SimpleNamespace(
            observed_at=start + timedelta(seconds=120),
            mqtt_frigate_age_seconds=180.0,
            mqtt_frigate_count=100,
            mqtt_birdnet_age_seconds=0.5,
        ),
        SimpleNamespace(
            observed_at=resume,
            mqtt_frigate_age_seconds=0.6,
            mqtt_frigate_count=140,
            mqtt_birdnet_age_seconds=0.4,
        ),
    ]
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "Frigate topic message growth below threshold (-163 < 1).",
            "MQTT topic-liveness reconnect growth below threshold (0 < 1).",
        ],
        "topic_liveness_reconnects_delta": 0,
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=True,
        samples=samples,
        induced_frigate_stall_at=start.isoformat(),
        resumed_frigate_at=resume.isoformat(),
        birdnet_publish_stats={"published": 20, "publish_failures": 0, "connect_failures": 0},
        max_birdnet_active_age_seconds=20.0,
        min_stall_duration_seconds=30.0,
    )

    assert normalized["passed"] is True
    assert normalized["failure_reasons"] == []
    assert normalized["frigate_stall_effective"] is True
    assert normalized["birdnet_stayed_fresh_during_stall"] is True


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
    resume = start + timedelta(seconds=60)
    samples = [
        SimpleNamespace(observed_at=start, mqtt_birdnet_age_seconds=4.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=30), mqtt_birdnet_age_seconds=6.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=60), mqtt_birdnet_age_seconds=8.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=120), mqtt_birdnet_age_seconds=45.0),
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
        resumed_frigate_at=resume.isoformat(),
        birdnet_publish_stats={"published": 20, "publish_failures": 0, "connect_failures": 0},
        max_birdnet_active_age_seconds=20.0,
    )

    assert normalized["passed"] is True
    assert normalized["failure_reasons"] == []
    assert normalized["birdnet_publisher_ok"] is True
    assert normalized["birdnet_stall_window_samples"] == 3
    assert normalized["birdnet_stayed_fresh_during_stall"] is True


def test_normalize_issue33_evaluation_ignores_missing_birdnet_age_sample_during_stall():
    start = datetime(2026, 4, 5, 6, 21, 0, tzinfo=timezone.utc)
    resume = start + timedelta(seconds=60)
    samples = [
        SimpleNamespace(observed_at=start, mqtt_birdnet_age_seconds=4.0),
        SimpleNamespace(observed_at=start + timedelta(seconds=20), mqtt_birdnet_age_seconds=None),
        SimpleNamespace(observed_at=start + timedelta(seconds=40), mqtt_birdnet_age_seconds=6.0),
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
        resumed_frigate_at=resume.isoformat(),
        birdnet_publish_stats={"published": 20, "publish_failures": 0, "connect_failures": 0},
        max_birdnet_active_age_seconds=20.0,
    )

    assert normalized["passed"] is True
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


def test_normalize_issue33_evaluation_fails_when_live_frigate_traffic_masks_stall():
    start = datetime(2026, 4, 5, 6, 21, 0, tzinfo=timezone.utc)
    samples = [
        SimpleNamespace(
            observed_at=start,
            mqtt_frigate_age_seconds=0.2,
            mqtt_frigate_count=100,
            mqtt_birdnet_age_seconds=0.2,
        ),
        SimpleNamespace(
            observed_at=start + timedelta(seconds=45),
            mqtt_frigate_age_seconds=0.3,
            mqtt_frigate_count=140,
            mqtt_birdnet_age_seconds=0.3,
        ),
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
        min_stall_duration_seconds=30.0,
    )

    assert normalized["passed"] is False
    assert any(
        reason.startswith("Live Frigate traffic remained active during the induced stall window.")
        for reason in normalized["failure_reasons"]
    )
    assert normalized["frigate_stall_effective"] is False


def test_normalize_issue33_evaluation_maintenance_scenario_ignores_mqtt_threshold_failures():
    evaluation = {
        "passed": False,
        "failure_reasons": [
            "BirdNET topic message growth below threshold (8 < 10).",
            "MQTT topic-liveness reconnect growth below threshold (0 < 1).",
        ],
    }

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        scenario="maintenance-video-timeout",
        induced_frigate_stall=False,
    )

    assert normalized["passed"] is True
    assert normalized["failure_reasons"] == []


def test_evaluate_issue33_tracks_flags_maintenance_video_timeout_from_workspace():
    health_evaluation = {"passed": True, "failure_reasons": []}
    workspace = {
        "focused_diagnostics": {
            "video_classifier": {
                "likely_last_error": "video_timeout",
                "candidate_failure_events": [
                    {
                        "reason_code": "video_timeout",
                        "context": {"source": "maintenance", "camera": "birdfeeder"},
                    }
                ],
                "recent_events": [
                    {
                        "reason_code": "video_circuit_opened",
                        "context": {"last_error": "video_timeout", "source": "maintenance"},
                    }
                ],
            }
        },
        "backend_diagnostics": {"events": []},
    }

    tracks = issue33._evaluate_issue33_tracks(
        scenario="combined",
        health_evaluation=health_evaluation,
        diagnostics_workspace=workspace,
    )

    assert tracks["maintenance_video_timeout"]["failed"] is True
    assert tracks["maintenance_video_timeout"]["reason"] == "maintenance_video_timeout_detected"
    assert tracks["mqtt_no_frigate_resume"]["failed"] is False


def test_normalize_issue33_evaluation_requires_inference_health_payload():
    evaluation = {"passed": True, "failure_reasons": []}

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        scenario="combined",
        induced_frigate_stall=False,
        samples=[],
        require_inference_health=True,
    )

    assert normalized["passed"] is False
    assert "Inference health telemetry missing from /health samples." in normalized["failure_reasons"]


def test_normalize_issue33_evaluation_summarizes_inference_health_payload():
    evaluation = {"passed": True, "failure_reasons": []}
    samples = [
        issue33.sample_from_health_payload(
            {
                "status": "ok",
                "mqtt": {},
                "ml": {
                    "inference_health": {
                        "status": "ok",
                        "runtimes": {
                            "openvino/intel_gpu/eu_medium_focalnet_b": {
                                "verdict": "healthy",
                                "samples": 3,
                            }
                        },
                    }
                },
            },
            observed_at=datetime(2026, 4, 24, 12, 0, tzinfo=timezone.utc),
        )
    ]

    normalized = issue33._normalize_issue33_evaluation(
        evaluation,
        scenario="combined",
        induced_frigate_stall=False,
        samples=samples,
    )

    assert normalized["passed"] is True
    assert normalized["inference_health_observed"] is True
    assert normalized["inference_health_status"] == "ok"
    assert normalized["inference_health_runtime_count"] == 1
    assert normalized["inference_health_total_samples"] == 3


def test_evaluate_issue33_tracks_flags_mqtt_no_resume_from_workspace_events():
    health_evaluation = {"passed": True, "failure_reasons": []}
    workspace = {
        "focused_diagnostics": {"video_classifier": {}},
        "backend_diagnostics": {
            "events": [
                {
                    "reason_code": "frigate_recovery_no_frigate_resume",
                    "context": {"consecutive_reconnects_without_frigate": 3},
                }
            ]
        },
    }

    tracks = issue33._evaluate_issue33_tracks(
        scenario="combined",
        health_evaluation=health_evaluation,
        diagnostics_workspace=workspace,
    )

    assert tracks["mqtt_no_frigate_resume"]["failed"] is True
    assert tracks["mqtt_no_frigate_resume"]["reason"] == "mqtt_no_frigate_resume_detected"
    assert tracks["maintenance_video_timeout"]["failed"] is False


def test_evaluate_issue33_tracks_ignores_taxonomy_collateral_without_backend_root_cause():
    health_evaluation = {"passed": True, "failure_reasons": []}
    workspace = {
        "focused_diagnostics": {
            "video_classifier": {
                "likely_last_error": None,
                "candidate_failure_events": [],
                "recent_events": [],
            }
        },
        "backend_diagnostics": {"events": []},
        "job_state": {
            "taxonomy": {"stale": True},
            "batch_analysis": {"stale": True},
        },
    }

    tracks = issue33._evaluate_issue33_tracks(
        scenario="combined",
        health_evaluation=health_evaluation,
        diagnostics_workspace=workspace,
    )

    assert tracks["maintenance_video_timeout"]["failed"] is False
    assert tracks["mqtt_no_frigate_resume"]["failed"] is False


def test_evaluate_issue33_tracks_replays_apr5_mixed_runtime_shape():
    health_evaluation = {
        "passed": True,
        "failure_reasons": [],
        "topic_liveness_reconnects_delta": 6,
        "video_failure_count_delta": 0,
    }
    workspace = {
        "focused_diagnostics": {
            "video_classifier": {
                "likely_last_error": "video_timeout",
                "candidate_failure_events": [
                    {
                        "timestamp": "2026-04-05T15:49:57.573831+00:00",
                        "reason_code": "video_timeout",
                        "context": {
                            "source": "maintenance",
                            "camera": "feeder_test",
                            "clip_bytes": 4888067,
                        },
                    }
                ],
                "recent_events": [
                    {
                        "timestamp": "2026-04-05T15:49:57.575560+00:00",
                        "reason_code": "video_circuit_opened",
                        "context": {
                            "last_error": "video_timeout",
                            "source": "maintenance",
                            "failure_count": 35,
                        },
                    }
                ],
            }
        },
        "backend_diagnostics": {
            "events": [
                {
                    "timestamp": "2026-04-05T18:11:09.714459+00:00",
                    "reason_code": "frigate_recovery_no_frigate_resume",
                    "context": {"consecutive_reconnects_without_frigate": 4},
                }
            ]
        },
    }

    tracks = issue33._evaluate_issue33_tracks(
        scenario="combined",
        health_evaluation=health_evaluation,
        diagnostics_workspace=workspace,
        run_started_at="2026-04-05T15:40:00+00:00",
    )

    assert tracks["maintenance_video_timeout"]["failed"] is True
    assert tracks["mqtt_no_frigate_resume"]["failed"] is True


def test_select_replay_seed_events_prefers_snapshot_and_clip_backed_birds():
    selected = issue33._select_replay_seed_events(
        [
            {"id": "no-snapshot", "label": "bird", "has_snapshot": False, "has_clip": True, "camera": "BirdCam"},
            {"id": "no-clip", "label": "bird", "has_snapshot": True, "has_clip": False, "camera": "BirdCam"},
            {"id": "cat-1", "label": "cat", "has_snapshot": True, "has_clip": True, "camera": "BirdCam"},
            {"id": "bird-1", "label": "bird", "has_snapshot": True, "has_clip": True, "camera": "BirdCam"},
            {"id": "bird-2", "label": "bird", "has_snapshot": True, "has_clip": True, "camera": "BirdCam"},
        ],
        limit=2,
        camera_name="BirdCam",
    )

    assert [item["id"] for item in selected] == ["bird-1", "bird-2"]


def test_build_replay_payload_factory_cycles_real_events():
    payload_factory = issue33._build_replay_payload_factory(
        [
            {"id": "evt-1", "camera": "BirdCam", "label": "bird", "start_time": 1.0, "end_time": 2.0},
            {"id": "evt-2", "camera": "BirdCam", "label": "bird", "start_time": 3.0, "end_time": 4.0},
        ]
    )

    first = payload_factory(0)
    second = payload_factory(1)
    third = payload_factory(2)

    assert '"id":"evt-1"' in first
    assert '"id":"evt-2"' in second
    assert '"id":"evt-1"' in third


def test_evaluate_issue33_tracks_filters_out_pre_run_stale_workspace_events():
    health_evaluation = {"passed": True, "failure_reasons": []}
    workspace = {
        "focused_diagnostics": {
            "video_classifier": {
                "likely_last_error": "video_timeout",
                "candidate_failure_events": [
                    {
                        "timestamp": "2026-04-04T08:47:50+00:00",
                        "reason_code": "video_timeout",
                        "context": {"source": "maintenance"},
                    }
                ],
                "recent_events": [],
            }
        },
        "backend_diagnostics": {
            "events": [
                {
                    "timestamp": "2026-04-04T18:11:09+00:00",
                    "reason_code": "frigate_recovery_no_frigate_resume",
                    "context": {"consecutive_reconnects_without_frigate": 4},
                }
            ]
        },
    }

    tracks = issue33._evaluate_issue33_tracks(
        scenario="combined",
        health_evaluation=health_evaluation,
        diagnostics_workspace=workspace,
        run_started_at="2026-04-05T15:40:00+00:00",
    )

    assert tracks["maintenance_video_timeout"]["failed"] is False
    assert tracks["mqtt_no_frigate_resume"]["failed"] is False
