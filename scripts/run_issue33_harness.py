#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
BACKEND_DIR = REPO_ROOT / "backend"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import run_issue22_soak as base_soak  # noqa: E402
from app.utils.issue22_soak_harness import (  # noqa: E402
    SoakThresholds,
    evaluate_soak_run,
    sample_from_health_payload,
)


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run issue #33 validation against YA-WAMF MQTT liveness and video-classifier recovery."
    )
    parser.add_argument(
        "--stress-profile",
        choices=["none", "issue33-live"],
        default="none",
        help="Apply a curated load profile for live issue #33 reproduction unless explicitly overridden.",
    )
    parser.add_argument(
        "--scenario",
        choices=["maintenance-video-timeout", "mqtt-no-frigate-resume", "combined"],
        default="combined",
    )
    parser.add_argument("--backend-url", default=os.getenv("SOAK_BACKEND_URL", "http://127.0.0.1:8946"))
    parser.add_argument("--health-path", default="/health")
    parser.add_argument("--analysis-path", default="/api/maintenance/analyze-unknowns")
    parser.add_argument("--diagnostics-workspace-path", default="/api/diagnostics/workspace")
    parser.add_argument("--auth-token", default=os.getenv("SOAK_AUTH_TOKEN"))
    parser.add_argument("--username", default=os.getenv("SOAK_USERNAME"))
    parser.add_argument("--password", default=os.getenv("SOAK_PASSWORD"))
    parser.add_argument("--login-path", default="/api/auth/login")
    parser.add_argument("--duration-seconds", type=int, default=900)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--http-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--trigger-analysis-interval-seconds", type=float, default=120.0)
    parser.add_argument("--induce-frigate-stall-after-seconds", type=float, default=180.0)
    parser.add_argument(
        "--frigate-stall-duration-seconds",
        type=float,
        default=0.0,
        help="How long to pause Frigate publishing after the induced stall starts. <= 0 keeps it paused for the rest of the run.",
    )
    parser.add_argument("--mqtt-host", default=os.getenv("SOAK_MQTT_HOST", os.getenv("MQTT_SERVER", "127.0.0.1")))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("SOAK_MQTT_PORT", os.getenv("MQTT_PORT", "1883"))))
    parser.add_argument("--mqtt-username", default=os.getenv("SOAK_MQTT_USERNAME", os.getenv("MQTT_USERNAME")))
    parser.add_argument("--mqtt-password", default=os.getenv("SOAK_MQTT_PASSWORD", os.getenv("MQTT_PASSWORD")))
    parser.add_argument("--mqtt-publish-container", default=os.getenv("SOAK_MQTT_PUBLISH_CONTAINER", ""))
    parser.add_argument("--frigate-api-url", default=os.getenv("SOAK_FRIGATE_API_URL", ""))
    parser.add_argument("--frigate-load-source", choices=["synthetic", "replay"], default="synthetic")
    parser.add_argument("--replay-frigate-event-id", action="append", default=[])
    parser.add_argument("--replay-frigate-seed-count", type=int, default=30)
    parser.add_argument("--replay-frigate-source-limit", type=int, default=200)
    parser.add_argument("--frigate-topic", default=os.getenv("SOAK_FRIGATE_TOPIC", "frigate/events"))
    parser.add_argument("--frigate-camera", default=os.getenv("SOAK_FRIGATE_CAMERA", ""))
    parser.add_argument("--birdnet-topic", default=os.getenv("SOAK_BIRDNET_TOPIC", ""))
    parser.add_argument("--disable-frigate-publisher", action="store_true")
    parser.add_argument("--disable-birdnet-publisher", action="store_true")
    parser.add_argument("--frigate-event-type", choices=["update", "new", "end"], default="update")
    parser.add_argument("--frigate-false-positive", action="store_true")
    parser.add_argument("--frigate-publish-interval-seconds", type=float, default=1.0)
    parser.add_argument("--birdnet-publish-interval-seconds", type=float, default=1.0)
    parser.add_argument("--frigate-publisher-replicas", type=int, default=1)
    parser.add_argument("--birdnet-publisher-replicas", type=int, default=1)
    parser.add_argument("--analysis-trigger-burst-count", type=int, default=1)
    parser.add_argument("--analysis-trigger-burst-spacing-seconds", type=float, default=0.0)
    parser.add_argument("--output-dir", default="")

    parser.add_argument("--min-samples", type=int, default=20)
    parser.add_argument("--max-health-fetch-failures", type=int, default=3)
    parser.add_argument("--min-frigate-delta", type=int, default=0)
    parser.add_argument("--min-birdnet-delta", type=int, default=10)
    parser.add_argument("--max-degraded-ratio", type=float, default=0.25)
    parser.add_argument("--max-pressure-level", choices=["normal", "elevated", "high", "critical"], default="high")
    parser.add_argument("--frigate-stall-age-seconds", type=float, default=120.0)
    parser.add_argument("--max-birdnet-active-age-seconds", type=float, default=20.0)
    parser.add_argument("--min-stall-duration-seconds", type=float, default=30.0)
    parser.add_argument("--min-reconnect-delta", type=int, default=1)
    parser.add_argument("--max-video-pending", type=int, default=25)
    parser.add_argument("--max-video-failure-count-delta", type=int, default=0)
    parser.add_argument("--allow-video-circuit-open", action="store_true")
    return parser


def _maybe_override_profile_value(
    args: argparse.Namespace,
    defaults: argparse.Namespace,
    field_name: str,
    value: Any,
) -> None:
    if getattr(args, field_name) == getattr(defaults, field_name):
        setattr(args, field_name, value)


def _apply_stress_profile(
    args: argparse.Namespace,
    *,
    parser: argparse.ArgumentParser | None = None,
) -> argparse.Namespace:
    if getattr(args, "stress_profile", "none") != "issue33-live":
        return args

    defaults = (parser or _build_arg_parser()).parse_args([])
    profile_overrides = {
        "duration_seconds": 1200,
        "poll_interval_seconds": 2.0,
        "trigger_analysis_interval_seconds": 15.0,
        "analysis_trigger_burst_count": 4,
        "analysis_trigger_burst_spacing_seconds": 0.75,
        "induce_frigate_stall_after_seconds": 120.0,
        "frigate_stall_duration_seconds": 420.0,
        "frigate_load_source": "replay",
        "frigate_event_type": "new",
        "frigate_publish_interval_seconds": 0.2,
        "birdnet_publish_interval_seconds": 0.25,
        "frigate_publisher_replicas": 4,
        "birdnet_publisher_replicas": 3,
        "max_pressure_level": "critical",
        "max_degraded_ratio": 0.5,
        "min_samples": 60,
    }
    for field_name, value in profile_overrides.items():
        _maybe_override_profile_value(args, defaults, field_name, value)
    return args


def _build_thresholds(args: argparse.Namespace) -> SoakThresholds:
    return SoakThresholds(
        min_samples=args.min_samples,
        min_frigate_messages_delta=args.min_frigate_delta,
        min_birdnet_messages_delta=args.min_birdnet_delta,
        max_degraded_ratio=args.max_degraded_ratio,
        max_pressure_level=args.max_pressure_level,
        frigate_stall_age_seconds=args.frigate_stall_age_seconds,
        max_birdnet_active_age_seconds=args.max_birdnet_active_age_seconds,
        min_stall_duration_seconds=args.min_stall_duration_seconds,
        max_health_fetch_failures=args.max_health_fetch_failures,
        min_topic_liveness_reconnects_delta=args.min_reconnect_delta,
        max_video_pending=args.max_video_pending,
        allow_video_circuit_open=args.allow_video_circuit_open,
        max_video_failure_count_delta=args.max_video_failure_count_delta,
    )


def _should_stop_frigate_publisher(*, elapsed_seconds: float, stop_after_seconds: float) -> bool:
    if stop_after_seconds <= 0:
        return False
    return elapsed_seconds >= stop_after_seconds


def _should_pause_frigate_publisher(
    *,
    elapsed_seconds: float,
    stop_after_seconds: float,
    stall_duration_seconds: float,
) -> bool:
    if stop_after_seconds <= 0 or elapsed_seconds < stop_after_seconds:
        return False
    if stall_duration_seconds <= 0:
        return True
    return elapsed_seconds < (stop_after_seconds + stall_duration_seconds)


def _publisher_replicas(disabled: bool, replicas: int) -> range:
    if disabled:
        return range(0)
    return range(max(0, replicas))


def _normalize_issue33_evaluation(
    evaluation: dict[str, Any],
    *,
    scenario: str = "combined",
    induced_frigate_stall: bool,
    samples: list[Any] | None = None,
    induced_frigate_stall_at: str | None = None,
    birdnet_publish_stats: dict[str, Any] | None = None,
    max_birdnet_active_age_seconds: float | None = None,
    min_stall_duration_seconds: float | None = None,
) -> dict[str, Any]:
    normalized = dict(evaluation)
    filtered_reasons = list(normalized.get("failure_reasons") or [])

    if scenario == "maintenance-video-timeout":
        filtered_reasons = [
            reason
            for reason in filtered_reasons
            if not (
                reason.startswith("Frigate topic message growth below threshold ")
                or reason.startswith("Frigate stream stalled while BirdNET remained active ")
                or reason.startswith("BirdNET topic message growth below threshold ")
                or reason.startswith("MQTT topic-liveness reconnect growth below threshold ")
            )
        ]

    if induced_frigate_stall:
        filtered_reasons = [
            reason
            for reason in filtered_reasons
            if not (
                reason.startswith("Frigate topic message growth below threshold ")
                or reason.startswith("Frigate stream stalled while BirdNET remained active ")
                or reason.startswith("BirdNET topic message growth below threshold ")
            )
        ]

    birdnet_state = _assess_issue33_birdnet_liveness(
        samples=samples or [],
        induced_frigate_stall=induced_frigate_stall,
        induced_frigate_stall_at=induced_frigate_stall_at,
        birdnet_publish_stats=birdnet_publish_stats or {},
        max_birdnet_active_age_seconds=max_birdnet_active_age_seconds,
    )
    if birdnet_state["failure_reason"]:
        filtered_reasons.append(str(birdnet_state["failure_reason"]))

    frigate_state = _assess_issue33_frigate_stall_effectiveness(
        samples=samples or [],
        induced_frigate_stall=induced_frigate_stall,
        induced_frigate_stall_at=induced_frigate_stall_at,
        min_stall_duration_seconds=min_stall_duration_seconds,
    )
    if frigate_state["failure_reason"]:
        filtered_reasons.append(str(frigate_state["failure_reason"]))

    normalized["failure_reasons"] = filtered_reasons
    normalized["passed"] = len(filtered_reasons) == 0
    normalized["birdnet_publisher_ok"] = birdnet_state["publisher_ok"]
    normalized["birdnet_stall_window_samples"] = birdnet_state["stall_window_samples"]
    normalized["birdnet_stayed_fresh_during_stall"] = birdnet_state["stayed_fresh"]
    normalized["frigate_stall_effective"] = frigate_state["stall_effective"]
    normalized["frigate_stall_window_samples"] = frigate_state["stall_window_samples"]
    return normalized


def _assess_issue33_birdnet_liveness(
    *,
    samples: list[Any],
    induced_frigate_stall: bool,
    induced_frigate_stall_at: str | None,
    birdnet_publish_stats: dict[str, Any],
    max_birdnet_active_age_seconds: float | None,
) -> dict[str, Any]:
    if not samples and not birdnet_publish_stats:
        return {
            "publisher_ok": True,
            "stall_window_samples": 0,
            "stayed_fresh": True,
            "failure_reason": None,
        }

    published = int(birdnet_publish_stats.get("published") or 0)
    publish_failures = int(birdnet_publish_stats.get("publish_failures") or 0)
    connect_failures = int(birdnet_publish_stats.get("connect_failures") or 0)
    publisher_ok = published > 0 and publish_failures == 0 and connect_failures == 0

    if not induced_frigate_stall:
        return {
            "publisher_ok": publisher_ok,
            "stall_window_samples": 0,
            "stayed_fresh": True,
            "failure_reason": None,
        }

    if not publisher_ok:
        return {
            "publisher_ok": False,
            "stall_window_samples": 0,
            "stayed_fresh": False,
            "failure_reason": "Synthetic BirdNET publisher did not produce healthy traffic.",
        }

    if not induced_frigate_stall_at or max_birdnet_active_age_seconds is None:
        return {
            "publisher_ok": True,
            "stall_window_samples": 0,
            "stayed_fresh": True,
            "failure_reason": None,
        }

    stall_started_at = datetime.fromisoformat(induced_frigate_stall_at)
    stall_samples = [sample for sample in samples if getattr(sample, "observed_at", stall_started_at) >= stall_started_at]
    if not stall_samples:
        return {
            "publisher_ok": True,
            "stall_window_samples": 0,
            "stayed_fresh": False,
            "failure_reason": "No health samples were captured during the induced Frigate stall window.",
        }

    stayed_fresh = all(
        getattr(sample, "mqtt_birdnet_age_seconds", None) is not None
        and float(getattr(sample, "mqtt_birdnet_age_seconds")) <= max_birdnet_active_age_seconds
        for sample in stall_samples
    )
    return {
        "publisher_ok": True,
        "stall_window_samples": len(stall_samples),
        "stayed_fresh": stayed_fresh,
        "failure_reason": None if stayed_fresh else "BirdNET did not stay fresh during the induced Frigate stall window.",
    }


def _assess_issue33_frigate_stall_effectiveness(
    *,
    samples: list[Any],
    induced_frigate_stall: bool,
    induced_frigate_stall_at: str | None,
    min_stall_duration_seconds: float | None,
) -> dict[str, Any]:
    if not induced_frigate_stall or not induced_frigate_stall_at or not samples:
        return {
            "stall_effective": True,
            "stall_window_samples": 0,
            "failure_reason": None,
        }

    stall_started_at = datetime.fromisoformat(induced_frigate_stall_at)
    stall_samples = [sample for sample in samples if getattr(sample, "observed_at", stall_started_at) >= stall_started_at]
    if not stall_samples:
        return {
            "stall_effective": True,
            "stall_window_samples": 0,
            "failure_reason": None,
        }

    observation_seconds = max(
        0.0,
        (getattr(stall_samples[-1], "observed_at", stall_started_at) - stall_started_at).total_seconds(),
    )
    required_window = max(10.0, float(min_stall_duration_seconds or 0.0))
    if observation_seconds < required_window:
        return {
            "stall_effective": True,
            "stall_window_samples": len(stall_samples),
            "failure_reason": None,
        }

    frigate_ages = [
        float(age)
        for age in (getattr(sample, "mqtt_frigate_age_seconds", None) for sample in stall_samples)
        if age is not None
    ]
    frigate_counts = [
        int(count)
        for count in (getattr(sample, "mqtt_frigate_count", None) for sample in stall_samples)
        if count is not None
    ]
    if not frigate_ages or len(frigate_counts) < 2:
        return {
            "stall_effective": True,
            "stall_window_samples": len(stall_samples),
            "failure_reason": None,
        }

    max_frigate_age = max(frigate_ages)
    frigate_count_delta = max(frigate_counts) - min(frigate_counts)
    if max_frigate_age < 10.0 and frigate_count_delta > 0:
        return {
            "stall_effective": False,
            "stall_window_samples": len(stall_samples),
            "failure_reason": (
                "Live Frigate traffic remained active during the induced stall window. "
                "The synthetic stall was masked, so MQTT stall-recovery was not actually exercised."
            ),
        }

    return {
        "stall_effective": True,
        "stall_window_samples": len(stall_samples),
        "failure_reason": None,
    }


def _request_json_with_body(
    method: str,
    url: str,
    timeout_seconds: float,
    payload: dict[str, Any],
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    request = Request(
        url=url,
        method=method.upper(),
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
        },
        data=body,
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = response.read()
    return json.loads(response_payload.decode("utf-8"))


def _fetch_owner_settings(
    *,
    backend_url: str,
    token: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = urljoin(f"{backend_url.rstrip('/')}/", "api/settings")
    request = Request(
        url=url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = response.read()
    payload = json.loads(response_payload.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Settings response was not a JSON object")
    return payload


def _fetch_diagnostics_workspace(
    *,
    backend_url: str,
    token: str,
    timeout_seconds: float,
    diagnostics_workspace_path: str = "/api/diagnostics/workspace",
) -> dict[str, Any]:
    url = urljoin(f"{backend_url.rstrip('/')}/", diagnostics_workspace_path.lstrip("/"))
    request = Request(
        url=url,
        method="GET",
        headers={
            "Accept": "application/json",
            "Authorization": f"Bearer {token}",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:
        response_payload = response.read()
    payload = json.loads(response_payload.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Diagnostics workspace response was not a JSON object")
    return payload


def _login_for_owner_token(
    *,
    backend_url: str,
    username: str,
    password: str,
    timeout_seconds: float,
    login_path: str = "/api/auth/login",
) -> str:
    url = urljoin(f"{backend_url.rstrip('/')}/", login_path.lstrip("/"))
    try:
        payload = _request_json_with_body(
            "POST",
            url,
            timeout_seconds,
            {
                "username": username,
                "password": password,
            },
        )
    except HTTPError as exc:
        raise ValueError(
            f"Owner login failed with HTTP {exc.code} at {url}"
        ) from exc
    except URLError as exc:
        raise ValueError(f"Owner login request failed for {url}: {exc.reason}") from exc
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError(f"Owner login returned an invalid JSON response from {url}") from exc
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise ValueError("Login response did not include access_token")
    return token


def _resolve_auth_token(args: argparse.Namespace) -> str | None:
    explicit_token = str(args.auth_token or "").strip()
    if explicit_token:
        return explicit_token

    username = str(args.username or "").strip()
    password = str(args.password or "")
    if not username and not password:
        return None
    if not username or not password:
        raise ValueError("Both --username and --password are required when using credential-based login")

    return _login_for_owner_token(
        backend_url=args.backend_url,
        username=username,
        password=password,
        timeout_seconds=args.http_timeout_seconds,
        login_path=args.login_path,
    )


def _resolve_birdnet_topic(args: argparse.Namespace, *, auth_token: str | None) -> str:
    explicit_topic = str(args.birdnet_topic or "").strip()
    if explicit_topic:
        return explicit_topic
    if not auth_token:
        return "birdnet"
    try:
        settings_payload = _fetch_owner_settings(
            backend_url=args.backend_url,
            token=auth_token,
            timeout_seconds=args.http_timeout_seconds,
        )
    except Exception:
        return "birdnet"
    topic = str(settings_payload.get("audio_topic") or "").strip()
    return topic or "birdnet"


def _resolve_frigate_camera(args: argparse.Namespace, *, auth_token: str | None) -> str:
    explicit_camera = str(args.frigate_camera or "").strip()
    if explicit_camera:
        return explicit_camera
    if not auth_token:
        return "BirdCam"
    try:
        settings_payload = _fetch_owner_settings(
            backend_url=args.backend_url,
            token=auth_token,
            timeout_seconds=args.http_timeout_seconds,
        )
    except Exception:
        return "BirdCam"
    cameras = settings_payload.get("cameras")
    if isinstance(cameras, list):
        for camera in cameras:
            camera_name = str(camera or "").strip()
            if camera_name:
                return camera_name
    return "BirdCam"


def _resolve_frigate_api_url(args: argparse.Namespace, *, auth_token: str | None) -> str:
    explicit_url = str(args.frigate_api_url or "").strip()
    if explicit_url:
        return explicit_url
    if not auth_token:
        return ""
    try:
        settings_payload = _fetch_owner_settings(
            backend_url=args.backend_url,
            token=auth_token,
            timeout_seconds=args.http_timeout_seconds,
        )
    except Exception:
        return ""
    return str(settings_payload.get("frigate_url") or "").strip()


def _select_replay_seed_events(
    frigate_events: list[dict[str, Any]],
    *,
    limit: int,
    camera_name: str | None = None,
    explicit_event_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    explicit_lookup = {event_id for event_id in (explicit_event_ids or []) if event_id}
    by_id = {
        str(event.get("id")): event
        for event in frigate_events
        if isinstance(event, dict) and event.get("id")
    }
    if explicit_lookup:
        for event_id in explicit_event_ids or []:
            event = by_id.get(str(event_id))
            if isinstance(event, dict):
                selected.append(event)
        return selected

    wanted_camera = str(camera_name or "").strip()
    for event in frigate_events:
        if not isinstance(event, dict):
            continue
        if event.get("label") != "bird":
            continue
        if not event.get("has_snapshot") or not event.get("has_clip"):
            continue
        if wanted_camera and str(event.get("camera") or "").strip() != wanted_camera:
            continue
        selected.append(event)
        if len(selected) >= limit:
            break
    return selected


def _build_replay_payload_factory(seed_events: list[dict[str, Any]]):
    if not seed_events:
        raise ValueError("seed_events must not be empty")

    def _payload_factory(sequence: int) -> str:
        event = seed_events[sequence % len(seed_events)]
        return base_soak._build_frigate_replay_payload(event)

    return _payload_factory


def _coerce_workspace_snapshots(diagnostics_workspace: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if isinstance(diagnostics_workspace, list):
        return [snapshot for snapshot in diagnostics_workspace if isinstance(snapshot, dict)]
    if isinstance(diagnostics_workspace, dict):
        return [diagnostics_workspace]
    return []


def _event_timestamp_is_in_run(event: dict[str, Any], run_started_at: str | None) -> bool:
    if not run_started_at:
        return True
    event_ts = str(event.get("timestamp") or "").strip()
    if not event_ts:
        return True
    return event_ts >= run_started_at


def _evaluate_issue33_tracks(
    *,
    scenario: str,
    health_evaluation: dict[str, Any],
    diagnostics_workspace: dict[str, Any] | list[dict[str, Any]] | None,
    run_started_at: str | None = None,
) -> dict[str, dict[str, Any]]:
    del health_evaluation
    snapshots = _coerce_workspace_snapshots(diagnostics_workspace)

    maintenance_failed = False
    maintenance_evidence: dict[str, Any] | None = None
    mqtt_failed = False
    mqtt_evidence: dict[str, Any] | None = None

    for snapshot in snapshots:
        focused = snapshot.get("focused_diagnostics") if isinstance(snapshot, dict) else {}
        focused_video = focused.get("video_classifier") if isinstance(focused, dict) else {}
        if isinstance(focused_video, dict):
            likely_last_error = str(focused_video.get("likely_last_error") or "").strip().lower()
            candidate_failure_events = focused_video.get("candidate_failure_events")
            recent_events = focused_video.get("recent_events")
            events = []
            if isinstance(candidate_failure_events, list):
                events.extend(event for event in candidate_failure_events if isinstance(event, dict))
            if isinstance(recent_events, list):
                events.extend(event for event in recent_events if isinstance(event, dict))
            for event in events:
                if not _event_timestamp_is_in_run(event, run_started_at):
                    continue
                reason_code = str(event.get("reason_code") or "").strip().lower()
                context = event.get("context") if isinstance(event.get("context"), dict) else {}
                source = str(context.get("source") or "").strip().lower()
                last_error = str(context.get("last_error") or "").strip().lower()
                if (
                    source == "maintenance"
                    and (
                        reason_code == "video_timeout"
                        or likely_last_error == "video_timeout"
                        or last_error == "video_timeout"
                    )
                ):
                    maintenance_failed = True
                    maintenance_evidence = event
                    break
        if maintenance_failed:
            break

    for snapshot in snapshots:
        backend_diagnostics = snapshot.get("backend_diagnostics") if isinstance(snapshot, dict) else {}
        events = backend_diagnostics.get("events") if isinstance(backend_diagnostics, dict) else []
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict) or not _event_timestamp_is_in_run(event, run_started_at):
                continue
            if str(event.get("reason_code") or "").strip().lower() == "frigate_recovery_no_frigate_resume":
                mqtt_failed = True
                mqtt_evidence = event
                break
        if mqtt_failed:
            break

    tracks = {
        "maintenance_video_timeout": {
            "checked": scenario in {"maintenance-video-timeout", "combined"},
            "failed": maintenance_failed if scenario in {"maintenance-video-timeout", "combined"} else False,
            "reason": "maintenance_video_timeout_detected" if maintenance_failed else None,
            "evidence": maintenance_evidence,
        },
        "mqtt_no_frigate_resume": {
            "checked": scenario in {"mqtt-no-frigate-resume", "combined"},
            "failed": mqtt_failed if scenario in {"mqtt-no-frigate-resume", "combined"} else False,
            "reason": "mqtt_no_frigate_resume_detected" if mqtt_failed else None,
            "evidence": mqtt_evidence,
        },
    }
    return tracks


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    args = _apply_stress_profile(args, parser=parser)
    thresholds = _build_thresholds(args)
    try:
        auth_token = _resolve_auth_token(args)
    except ValueError as exc:
        parser.error(str(exc))
    args.birdnet_topic = _resolve_birdnet_topic(args, auth_token=auth_token)
    args.frigate_camera = _resolve_frigate_camera(args, auth_token=auth_token)
    args.frigate_api_url = _resolve_frigate_api_url(args, auth_token=auth_token)

    run_started_at = base_soak._now_utc()
    run_label = run_started_at.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / "tmp" / "issue33-harness" / run_label
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "samples.ndjson"
    summary_path = output_dir / "summary.json"

    base_soak._log(f"Starting issue #33 harness for {args.duration_seconds}s")
    base_soak._log(f"Artifacts: {output_dir}")

    stop_event = threading.Event()
    frigate_stop_event = threading.Event()
    frigate_pause_event = threading.Event()
    frigate_stats = base_soak.PublisherStats()
    birdnet_stats = base_soak.PublisherStats()
    induced_frigate_stall_at: str | None = None
    resumed_frigate_at: str | None = None
    replay_seed_events: list[dict[str, Any]] = []

    def _handle_signal(_signum, _frame) -> None:
        base_soak._log("Received termination signal; stopping issue #33 harness.")
        stop_event.set()
        frigate_stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    frigate_threads: list[threading.Thread] = []
    birdnet_threads: list[threading.Thread] = []

    frigate_payload_factory = None
    if not args.disable_frigate_publisher:
        if args.frigate_load_source == "replay":
            if not args.frigate_api_url:
                parser.error("--frigate-api-url is required when --frigate-load-source replay is enabled")
            frigate_events = base_soak._fetch_frigate_events(
                args.frigate_api_url,
                timeout_seconds=args.http_timeout_seconds,
                limit=max(args.replay_frigate_source_limit, args.replay_frigate_seed_count),
            )
            replay_seed_events = _select_replay_seed_events(
                frigate_events,
                limit=args.replay_frigate_seed_count,
                camera_name=args.frigate_camera,
                explicit_event_ids=list(args.replay_frigate_event_id),
            )
            if not replay_seed_events:
                parser.error("Unable to discover any replayable Frigate events for the selected camera")
            frigate_payload_factory = _build_replay_payload_factory(replay_seed_events)
            base_soak._log(
                "Using replay-backed Frigate load "
                f"({len(replay_seed_events)} seed event(s), camera={args.frigate_camera})"
            )
        else:
            frigate_payload_factory = lambda seq: base_soak._build_frigate_payload(
                event_id=f"issue33-{run_label}-r0-{seq}",
                camera=args.frigate_camera,
                event_type=args.frigate_event_type,
                false_positive=args.frigate_false_positive,
            )

    for replica in _publisher_replicas(args.disable_frigate_publisher, args.frigate_publisher_replicas):
        frigate_thread = threading.Thread(
            target=base_soak._publisher_loop,
            kwargs={
                "stop_event": frigate_stop_event,
                "stats": frigate_stats,
                "mqtt_host": args.mqtt_host,
                "mqtt_port": args.mqtt_port,
                "mqtt_username": args.mqtt_username,
                "mqtt_password": args.mqtt_password,
                "topic": args.frigate_topic,
                "payload_factory": (
                    frigate_payload_factory
                    if args.frigate_load_source == "replay"
                    else (
                        lambda seq, replica_id=replica: base_soak._build_frigate_payload(
                            event_id=f"issue33-{run_label}-r{replica_id}-{seq}",
                            camera=args.frigate_camera,
                            event_type=args.frigate_event_type,
                            false_positive=args.frigate_false_positive,
                        )
                    )
                ),
                "interval_seconds": max(0.05, args.frigate_publish_interval_seconds),
                "client_id_prefix": f"issue33-frigate-r{replica}",
                "publish_container": args.mqtt_publish_container or None,
                "pause_event": frigate_pause_event,
            },
            daemon=True,
        )
        frigate_thread.start()
        frigate_threads.append(frigate_thread)

    for replica in _publisher_replicas(args.disable_birdnet_publisher, args.birdnet_publisher_replicas):
        birdnet_thread = threading.Thread(
            target=base_soak._publisher_loop,
            kwargs={
                "stop_event": stop_event,
                "stats": birdnet_stats,
                "mqtt_host": args.mqtt_host,
                "mqtt_port": args.mqtt_port,
                "mqtt_username": args.mqtt_username,
                "mqtt_password": args.mqtt_password,
                "topic": args.birdnet_topic,
                "payload_factory": lambda seq, replica_id=replica: base_soak._build_birdnet_payload(
                    (replica_id * 1_000_000) + seq
                ),
                "interval_seconds": max(0.05, args.birdnet_publish_interval_seconds),
                "client_id_prefix": f"issue33-birdnet-r{replica}",
                "publish_container": args.mqtt_publish_container or None,
            },
            daemon=True,
        )
        birdnet_thread.start()
        birdnet_threads.append(birdnet_thread)

    samples = []
    diagnostics_workspace_snapshots: list[dict[str, Any]] = []
    analysis_triggers: list[dict[str, Any]] = []
    health_fetch_failures = 0
    deadline = time.time() + max(1, args.duration_seconds)
    next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds if args.trigger_analysis_interval_seconds > 0 else None

    while not stop_event.is_set() and time.time() < deadline:
        tick_started = time.time()
        elapsed = tick_started - run_started_at.timestamp()
        observed_at = base_soak._now_utc()

        if (
            not args.disable_frigate_publisher
            and _should_pause_frigate_publisher(
                elapsed_seconds=elapsed,
                stop_after_seconds=args.induce_frigate_stall_after_seconds,
                stall_duration_seconds=args.frigate_stall_duration_seconds,
            )
        ):
            if not frigate_pause_event.is_set():
                frigate_pause_event.set()
                induced_frigate_stall_at = observed_at.isoformat()
                base_soak._write_ndjson_line(
                    samples_path,
                    {
                        "type": "frigate_publisher_paused",
                        "observed_at": induced_frigate_stall_at,
                        "elapsed_seconds": round(elapsed, 1),
                    },
                )
        elif frigate_pause_event.is_set():
            frigate_pause_event.clear()
            resumed_frigate_at = observed_at.isoformat()
            base_soak._write_ndjson_line(
                samples_path,
                {
                    "type": "frigate_publisher_resumed",
                    "observed_at": resumed_frigate_at,
                    "elapsed_seconds": round(elapsed, 1),
                },
            )

        try:
            payload = base_soak._fetch_health(
                backend_url=args.backend_url,
                health_path=args.health_path,
                token=auth_token,
                timeout_seconds=args.http_timeout_seconds,
            )
            sample = sample_from_health_payload(payload, observed_at=observed_at)
            samples.append(sample)
            base_soak._write_ndjson_line(samples_path, {"type": "health_sample", **sample.to_json()})
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            health_fetch_failures += 1
            base_soak._write_ndjson_line(
                samples_path,
                {
                    "type": "health_fetch_error",
                    "observed_at": observed_at.isoformat(),
                    "error": str(exc),
                },
            )

        if auth_token:
            try:
                workspace_payload = _fetch_diagnostics_workspace(
                    backend_url=args.backend_url,
                    token=auth_token,
                    timeout_seconds=args.http_timeout_seconds,
                    diagnostics_workspace_path=args.diagnostics_workspace_path,
                )
                diagnostics_workspace_snapshots.append(workspace_payload)
                base_soak._write_ndjson_line(
                    samples_path,
                    {
                        "type": "diagnostics_workspace",
                        "observed_at": observed_at.isoformat(),
                        "focused_video_likely_last_error": (
                            workspace_payload.get("focused_diagnostics", {})
                            .get("video_classifier", {})
                            .get("likely_last_error")
                        ),
                    },
                )
            except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
                base_soak._write_ndjson_line(
                    samples_path,
                    {
                        "type": "diagnostics_workspace_error",
                        "observed_at": observed_at.isoformat(),
                        "error": str(exc),
                    },
                )

        if next_analysis_trigger is not None and time.time() >= next_analysis_trigger:
            for burst_index in range(max(1, args.analysis_trigger_burst_count)):
                trigger_time = base_soak._now_utc()
                try:
                    response = base_soak._trigger_unknown_analysis(
                        backend_url=args.backend_url,
                        analysis_path=args.analysis_path,
                        token=auth_token,
                        timeout_seconds=args.http_timeout_seconds,
                    )
                    trigger_result = {
                        "observed_at": trigger_time.isoformat(),
                        "ok": True,
                        "burst_index": burst_index,
                        "response": response,
                    }
                except Exception as exc:  # pragma: no cover - integration path
                    trigger_result = {
                        "observed_at": trigger_time.isoformat(),
                        "ok": False,
                        "burst_index": burst_index,
                        "error": str(exc),
                    }
                analysis_triggers.append(trigger_result)
                base_soak._write_ndjson_line(samples_path, {"type": "analysis_trigger", **trigger_result})
                if (
                    burst_index + 1 < max(1, args.analysis_trigger_burst_count)
                    and args.analysis_trigger_burst_spacing_seconds > 0
                ):
                    time.sleep(args.analysis_trigger_burst_spacing_seconds)
            next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds

        time.sleep(max(0.0, args.poll_interval_seconds - (time.time() - tick_started)))

    stop_event.set()
    frigate_stop_event.set()
    for frigate_thread in frigate_threads:
        frigate_thread.join(timeout=5.0)
    for birdnet_thread in birdnet_threads:
        birdnet_thread.join(timeout=5.0)

    evaluation = evaluate_soak_run(samples, thresholds, health_fetch_failures=health_fetch_failures)
    evaluation = _normalize_issue33_evaluation(
        evaluation,
        scenario=args.scenario,
        induced_frigate_stall=(
            induced_frigate_stall_at is not None
        ),
        samples=samples,
        induced_frigate_stall_at=induced_frigate_stall_at,
        birdnet_publish_stats=asdict(birdnet_stats),
        max_birdnet_active_age_seconds=thresholds.max_birdnet_active_age_seconds,
        min_stall_duration_seconds=thresholds.min_stall_duration_seconds,
    )
    tracks = _evaluate_issue33_tracks(
        scenario=args.scenario,
        health_evaluation=evaluation,
        diagnostics_workspace=diagnostics_workspace_snapshots,
        run_started_at=run_started_at.isoformat(),
    )
    active_track_failures = [
        track["reason"]
        for track in tracks.values()
        if track.get("checked") and track.get("failed") and track.get("reason")
    ]
    if active_track_failures:
        merged_reasons = list(evaluation.get("failure_reasons") or [])
        for reason in active_track_failures:
            if reason not in merged_reasons:
                merged_reasons.append(str(reason))
        evaluation["failure_reasons"] = merged_reasons
        evaluation["passed"] = False
    run_finished_at = base_soak._now_utc()
    duration_actual_seconds = max(0.0, (run_finished_at - run_started_at).total_seconds())

    summary = {
        "issue": 33,
        "status": "pass" if evaluation["passed"] else "fail",
        "run_started_at": run_started_at.isoformat(),
        "run_finished_at": run_finished_at.isoformat(),
        "duration_seconds": round(duration_actual_seconds, 1),
        "config": {
            "backend_url": args.backend_url,
            "scenario": args.scenario,
            "health_path": args.health_path,
            "analysis_path": args.analysis_path,
            "diagnostics_workspace_path": args.diagnostics_workspace_path,
            "login_path": args.login_path,
            "duration_seconds": args.duration_seconds,
            "poll_interval_seconds": args.poll_interval_seconds,
            "trigger_analysis_interval_seconds": args.trigger_analysis_interval_seconds,
            "induce_frigate_stall_after_seconds": args.induce_frigate_stall_after_seconds,
            "frigate_stall_duration_seconds": args.frigate_stall_duration_seconds,
            "mqtt_host": args.mqtt_host,
            "mqtt_port": args.mqtt_port,
            "mqtt_publish_container": args.mqtt_publish_container,
            "frigate_api_url": args.frigate_api_url,
            "frigate_load_source": args.frigate_load_source,
            "replay_frigate_event_id": list(args.replay_frigate_event_id),
            "replay_frigate_seed_count": args.replay_frigate_seed_count,
            "replay_frigate_source_limit": args.replay_frigate_source_limit,
            "frigate_topic": args.frigate_topic,
            "frigate_camera": args.frigate_camera,
            "birdnet_topic": args.birdnet_topic,
            "disable_frigate_publisher": args.disable_frigate_publisher,
            "disable_birdnet_publisher": args.disable_birdnet_publisher,
            "frigate_event_type": args.frigate_event_type,
            "frigate_false_positive": args.frigate_false_positive,
            "frigate_publish_interval_seconds": args.frigate_publish_interval_seconds,
            "birdnet_publish_interval_seconds": args.birdnet_publish_interval_seconds,
            "frigate_publisher_replicas": args.frigate_publisher_replicas,
            "birdnet_publisher_replicas": args.birdnet_publisher_replicas,
            "analysis_trigger_burst_count": args.analysis_trigger_burst_count,
            "analysis_trigger_burst_spacing_seconds": args.analysis_trigger_burst_spacing_seconds,
            "stress_profile": args.stress_profile,
            "username": args.username,
            "used_auth_token": bool(auth_token),
            "thresholds": asdict(thresholds),
        },
        "publishers": {
            "frigate": asdict(frigate_stats),
            "birdnet": asdict(birdnet_stats),
        },
        "analysis_triggers": analysis_triggers,
        "induced_frigate_stall_at": induced_frigate_stall_at,
        "resumed_frigate_at": resumed_frigate_at,
        "replay": {
            "seed_count": len(replay_seed_events),
            "seed_event_ids": [str(event.get("id")) for event in replay_seed_events if event.get("id")],
            "seed_cameras": sorted({str(event.get("camera")) for event in replay_seed_events if event.get("camera")}),
        },
        "evaluation": evaluation,
        "tracks": tracks,
        "artifacts": {
            "samples_ndjson": str(samples_path),
            "summary_json": str(summary_path),
        },
        "note": "Harness collects validation evidence only. It does not close GitHub issues.",
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    base_soak._log(f"Completed issue #33 harness run: {summary['status'].upper()}")
    base_soak._log(f"Summary written to {summary_path}")

    if not evaluation["passed"]:
        for reason in evaluation["failure_reasons"]:
            base_soak._log(f"FAILURE: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
