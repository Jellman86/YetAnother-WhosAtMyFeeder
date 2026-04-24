#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, unquote, urljoin, urlparse
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
        choices=["none", "issue33-live", "issue33-stall-probe", "issue33-fixture-replay"],
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
    parser.add_argument("--frigate-load-source", choices=["synthetic", "replay", "fixture"], default="synthetic")
    parser.add_argument("--replay-frigate-event-id", action="append", default=[])
    parser.add_argument("--replay-frigate-seed-count", type=int, default=30)
    parser.add_argument("--replay-frigate-source-limit", type=int, default=200)
    parser.add_argument("--fixture-image-dir", default=os.getenv("ISSUE33_FIXTURE_IMAGE_DIR", ""))
    parser.add_argument("--fixture-event-count", type=int, default=6)
    parser.add_argument("--fixture-frigate-host", default="127.0.0.1")
    parser.add_argument("--fixture-frigate-port", type=int, default=8799)
    parser.add_argument("--fixture-clip-seconds", type=float, default=3.0)
    parser.add_argument("--trigger-backfill", action="store_true")
    parser.add_argument("--fixture-manual-tag-unknown", action="store_true")
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
    parser.add_argument("--min-backfill-processed", type=int, default=0)
    parser.add_argument("--min-analysis-total-candidates", type=int, default=0)
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
    profile = getattr(args, "stress_profile", "none")
    if profile == "none":
        return args

    defaults = (parser or _build_arg_parser()).parse_args([])
    if profile == "issue33-live":
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
    elif profile == "issue33-stall-probe":
        profile_overrides = {
            "duration_seconds": 900,
            "poll_interval_seconds": 2.0,
            "trigger_analysis_interval_seconds": 0.0,
            "analysis_trigger_burst_count": 1,
            "analysis_trigger_burst_spacing_seconds": 0.0,
            "induce_frigate_stall_after_seconds": 90.0,
            "frigate_stall_duration_seconds": 420.0,
            "frigate_load_source": "replay",
            "frigate_event_type": "new",
            "frigate_publish_interval_seconds": 0.75,
            "birdnet_publish_interval_seconds": 0.5,
            "frigate_publisher_replicas": 1,
            "birdnet_publisher_replicas": 1,
            "max_pressure_level": "high",
            "max_degraded_ratio": 0.35,
            "min_samples": 45,
        }
    elif profile == "issue33-fixture-replay":
        profile_overrides = {
            "duration_seconds": 240,
            "poll_interval_seconds": 2.0,
            "trigger_analysis_interval_seconds": 20.0,
            "analysis_trigger_burst_count": 2,
            "analysis_trigger_burst_spacing_seconds": 0.5,
            "induce_frigate_stall_after_seconds": 60.0,
            "frigate_stall_duration_seconds": 0.0,
            "frigate_load_source": "fixture",
            "frigate_event_type": "new",
            "frigate_publish_interval_seconds": 0.5,
            "birdnet_publish_interval_seconds": 0.5,
            "frigate_publisher_replicas": 2,
            "birdnet_publisher_replicas": 2,
            "trigger_backfill": True,
            "fixture_manual_tag_unknown": True,
            "min_backfill_processed": 3,
            "min_analysis_total_candidates": 1,
            "max_pressure_level": "critical",
            "max_degraded_ratio": 0.75,
            "min_samples": 60,
        }
    else:
        return args
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


_FIXTURE_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _discover_fixture_images(image_dir: str | Path) -> list[Path]:
    root = Path(image_dir)
    if not root.exists():
        raise FileNotFoundError(f"Fixture image directory does not exist: {root}")
    images = [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() in _FIXTURE_IMAGE_SUFFIXES
    ]
    return sorted(images, key=lambda path: str(path).lower())


def _build_fixture_events(
    *,
    images: list[Path],
    count: int,
    camera: str,
    run_label: str,
    now: datetime | None = None,
) -> list[dict[str, Any]]:
    if not images:
        raise ValueError("At least one fixture image is required")
    ts_now = now or base_soak._now_utc()
    event_count = max(1, int(count))
    events: list[dict[str, Any]] = []
    for index in range(event_count):
        event_id = f"issue33-fixture-{run_label}-{index + 1:04d}"
        start_time = (ts_now - timedelta(seconds=(event_count - index) * 20)).timestamp()
        end_time = start_time + 5.0
        image_path = images[index % len(images)]
        events.append(
            {
                "id": event_id,
                "camera": camera,
                "label": "bird",
                "sub_label": None,
                "start_time": start_time,
                "end_time": end_time,
                "top_score": 0.91,
                "score": 0.91,
                "false_positive": False,
                "has_snapshot": True,
                "has_clip": True,
                "data": {
                    "box": [20, 20, 300, 300],
                    "region": [0, 0, 320, 320],
                    "top_score": 0.91,
                },
                "_fixture_image_path": str(image_path),
            }
        )
    return events


def _generate_fixture_clip(
    *,
    image_path: Path,
    output_dir: Path,
    seconds: float,
) -> Path | None:
    clip_path = output_dir / "fixture-frigate-clip.mp4"
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-t",
        str(max(1.0, float(seconds))),
        "-vf",
        "scale=640:-2",
        "-pix_fmt",
        "yuv420p",
        str(clip_path),
    ]
    try:
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError):
        return None
    return clip_path if clip_path.exists() else None


class _FixtureFrigateServer:
    def __init__(
        self,
        *,
        host: str,
        port: int,
        events: list[dict[str, Any]],
        clip_path: Path | None,
    ) -> None:
        self.host = host
        self.port = int(port)
        self.events = events
        self.clip_path = clip_path
        self._httpd: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> str:
        events_by_id = {str(event["id"]): event for event in self.events}
        events = self.events
        clip_path = self.clip_path

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, format: str, *args: Any) -> None:
                return

            def _send_json(self, payload: Any, status: int = 200) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _send_bytes(self, payload: bytes, content_type: str, status: int = 200) -> None:
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def do_GET(self) -> None:
                parsed = urlparse(self.path)
                path = parsed.path.rstrip("/")
                if path == "/api/config":
                    cameras = sorted({str(event.get("camera")) for event in events if event.get("camera")})
                    self._send_json(
                        {
                            "cameras": {
                                camera: {"record": {"events": {"retain": {"default": 30}}}}
                                for camera in cameras
                            }
                        }
                    )
                    return
                if path == "/api/events":
                    query = parse_qs(parsed.query)
                    camera_filter = (query.get("camera") or [""])[0]
                    label_filter = (query.get("label") or [""])[0]
                    limit = int((query.get("limit") or [len(events)])[0])
                    filtered = []
                    for event in events:
                        if camera_filter and str(event.get("camera")) != camera_filter:
                            continue
                        if label_filter and str(event.get("label")) != label_filter:
                            continue
                        filtered.append({k: v for k, v in event.items() if not k.startswith("_")})
                    self._send_json(filtered[:limit])
                    return
                prefix = "/api/events/"
                if path.startswith(prefix):
                    remainder = path[len(prefix):]
                    if remainder.endswith("/snapshot.jpg"):
                        event_id = unquote(remainder[: -len("/snapshot.jpg")])
                        event = events_by_id.get(event_id)
                        if not event:
                            self._send_json({"message": "not found"}, status=404)
                            return
                        image_path = Path(str(event["_fixture_image_path"]))
                        self._send_bytes(image_path.read_bytes(), "image/jpeg")
                        return
                    if remainder.endswith("/clip.mp4"):
                        event_id = unquote(remainder[: -len("/clip.mp4")])
                        if event_id not in events_by_id:
                            self._send_json({"message": "not found"}, status=404)
                            return
                        if not clip_path or not clip_path.exists():
                            self._send_json({"message": "No recordings found for the specified time range"}, status=400)
                            return
                        self._send_bytes(clip_path.read_bytes(), "video/mp4")
                        return
                    event_id = unquote(remainder)
                    event = events_by_id.get(event_id)
                    if not event:
                        self._send_json({"message": "not found"}, status=404)
                        return
                    self._send_json({k: v for k, v in event.items() if not k.startswith("_")})
                    return
                self._send_json({"message": "not found"}, status=404)

        self._httpd = ThreadingHTTPServer((self.host, self.port), Handler)
        self.port = int(self._httpd.server_address[1])
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="issue33-fixture-frigate", daemon=True)
        self._thread.start()
        return f"http://{self.host}:{self.port}"

    def stop(self) -> None:
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5.0)


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


def _frigate_publishers_running(threads: list[threading.Thread]) -> bool:
    return any(thread.is_alive() for thread in threads)


def _set_frigate_publishers_running(
    *,
    should_run: bool,
    threads: list[threading.Thread],
    stop_event: threading.Event,
    start_publishers,
    join_timeout_seconds: float = 1.0,
) -> tuple[list[threading.Thread], threading.Event, bool]:
    running = _frigate_publishers_running(threads)

    if should_run:
        if running:
            return threads, stop_event, False
        if threads:
            stop_event.set()
            for thread in threads:
                thread.join(timeout=join_timeout_seconds)
        new_stop_event = threading.Event()
        return list(start_publishers(new_stop_event)), new_stop_event, True

    if not threads:
        return [], stop_event, False

    stop_event.set()
    for thread in threads:
        thread.join(timeout=join_timeout_seconds)
    return [], stop_event, True


def _normalize_issue33_evaluation(
    evaluation: dict[str, Any],
    *,
    scenario: str = "combined",
    induced_frigate_stall: bool,
    samples: list[Any] | None = None,
    induced_frigate_stall_at: str | None = None,
    resumed_frigate_at: str | None = None,
    birdnet_publish_stats: dict[str, Any] | None = None,
    max_birdnet_active_age_seconds: float | None = None,
    min_stall_duration_seconds: float | None = None,
    require_inference_health: bool = False,
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
                or reason.startswith("MQTT topic-liveness reconnect growth below threshold ")
            )
        ]

    birdnet_state = _assess_issue33_birdnet_liveness(
        samples=samples or [],
        induced_frigate_stall=induced_frigate_stall,
        induced_frigate_stall_at=induced_frigate_stall_at,
        resumed_frigate_at=resumed_frigate_at,
        birdnet_publish_stats=birdnet_publish_stats or {},
        max_birdnet_active_age_seconds=max_birdnet_active_age_seconds,
    )
    if birdnet_state["failure_reason"]:
        filtered_reasons.append(str(birdnet_state["failure_reason"]))

    frigate_state = _assess_issue33_frigate_stall_effectiveness(
        samples=samples or [],
        induced_frigate_stall=induced_frigate_stall,
        induced_frigate_stall_at=induced_frigate_stall_at,
        resumed_frigate_at=resumed_frigate_at,
        min_stall_duration_seconds=min_stall_duration_seconds,
    )
    if frigate_state["failure_reason"]:
        filtered_reasons.append(str(frigate_state["failure_reason"]))

    inference_state = _assess_issue33_inference_health(
        samples=samples or [],
        required=require_inference_health,
    )
    if inference_state["failure_reason"]:
        filtered_reasons.append(str(inference_state["failure_reason"]))

    normalized["failure_reasons"] = filtered_reasons
    normalized["passed"] = len(filtered_reasons) == 0
    normalized["birdnet_publisher_ok"] = birdnet_state["publisher_ok"]
    normalized["birdnet_stall_window_samples"] = birdnet_state["stall_window_samples"]
    normalized["birdnet_stayed_fresh_during_stall"] = birdnet_state["stayed_fresh"]
    normalized["frigate_stall_effective"] = frigate_state["stall_effective"]
    normalized["frigate_stall_window_samples"] = frigate_state["stall_window_samples"]
    normalized["inference_health_observed"] = inference_state["observed"]
    normalized["inference_health_status"] = inference_state["status"]
    normalized["inference_health_runtime_count"] = inference_state["runtime_count"]
    normalized["inference_health_unhealthy_runtime_count"] = inference_state["unhealthy_runtime_count"]
    normalized["inference_health_total_samples"] = inference_state["total_samples"]
    return normalized


def _assess_issue33_inference_health(*, samples: list[Any], required: bool) -> dict[str, Any]:
    observed_samples = [
        sample
        for sample in samples
        if getattr(sample, "inference_health_status", None) is not None
    ]
    if not observed_samples:
        return {
            "observed": False,
            "status": None,
            "runtime_count": None,
            "unhealthy_runtime_count": None,
            "total_samples": None,
            "failure_reason": "Inference health telemetry missing from /health samples." if required else None,
        }

    latest = observed_samples[-1]
    return {
        "observed": True,
        "status": getattr(latest, "inference_health_status", None),
        "runtime_count": getattr(latest, "inference_health_runtime_count", None),
        "unhealthy_runtime_count": getattr(latest, "inference_health_unhealthy_runtime_count", None),
        "total_samples": getattr(latest, "inference_health_total_samples", None),
        "failure_reason": None,
    }


def _assess_issue33_birdnet_liveness(
    *,
    samples: list[Any],
    induced_frigate_stall: bool,
    induced_frigate_stall_at: str | None,
    resumed_frigate_at: str | None,
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
    stall_ended_at = datetime.fromisoformat(resumed_frigate_at) if resumed_frigate_at else None
    stall_samples = [
        sample
        for sample in samples
        if getattr(sample, "observed_at", stall_started_at) >= stall_started_at
        and (stall_ended_at is None or getattr(sample, "observed_at", stall_started_at) <= stall_ended_at)
    ]
    if not stall_samples:
        return {
            "publisher_ok": True,
            "stall_window_samples": 0,
            "stayed_fresh": False,
            "failure_reason": "No health samples were captured during the induced Frigate stall window.",
        }

    birdnet_ages = [
        float(age)
        for age in (getattr(sample, "mqtt_birdnet_age_seconds", None) for sample in stall_samples)
        if age is not None
    ]
    if not birdnet_ages:
        return {
            "publisher_ok": True,
            "stall_window_samples": len(stall_samples),
            "stayed_fresh": False,
            "failure_reason": "No BirdNET age samples were captured during the induced Frigate stall window.",
        }

    stayed_fresh = all(age <= max_birdnet_active_age_seconds for age in birdnet_ages)
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
    resumed_frigate_at: str | None,
    min_stall_duration_seconds: float | None,
) -> dict[str, Any]:
    if not induced_frigate_stall or not induced_frigate_stall_at or not samples:
        return {
            "stall_effective": True,
            "stall_window_samples": 0,
            "failure_reason": None,
        }

    stall_started_at = datetime.fromisoformat(induced_frigate_stall_at)
    stall_ended_at = datetime.fromisoformat(resumed_frigate_at) if resumed_frigate_at else None
    stall_samples = [
        sample
        for sample in samples
        if getattr(sample, "observed_at", stall_started_at) >= stall_started_at
        and (stall_ended_at is None or getattr(sample, "observed_at", stall_started_at) <= stall_ended_at)
    ]
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
    token: str | None = None,
) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(
        url=url,
        method=method.upper(),
        headers=headers,
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


def _trigger_backfill(
    *,
    backend_url: str,
    token: str,
    timeout_seconds: float,
    start_date: str,
    end_date: str,
    cameras: list[str],
) -> dict[str, Any]:
    url = urljoin(f"{backend_url.rstrip('/')}/", "api/backfill")
    return _request_json_with_body(
        "POST",
        url,
        timeout_seconds,
        {
            "date_range": "custom",
            "start_date": start_date,
            "end_date": end_date,
            "cameras": cameras,
        },
        token=token,
    )


def _manual_tag_unknowns(
    *,
    backend_url: str,
    token: str,
    timeout_seconds: float,
    event_ids: list[str],
) -> dict[str, Any]:
    url = urljoin(f"{backend_url.rstrip('/')}/", "api/events/bulk/manual-tag")
    return _request_json_with_body(
        "PATCH",
        url,
        timeout_seconds,
        {
            "event_ids": event_ids,
            "display_name": "Unknown Bird",
        },
        token=token,
    )


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
        return "birdnet/text"
    try:
        settings_payload = _fetch_owner_settings(
            backend_url=args.backend_url,
            token=auth_token,
            timeout_seconds=args.http_timeout_seconds,
        )
    except Exception:
        return "birdnet/text"
    topic = str(settings_payload.get("audio_topic") or "").strip()
    return topic or "birdnet/text"


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
    allow_expected_mqtt_no_frigate_resume: bool = False,
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
            reason_code = str(event.get("reason_code") or "").strip().lower()
            if reason_code == "frigate_recovery_abandoned":
                mqtt_failed = True
                mqtt_evidence = event
                break
            if reason_code == "frigate_recovery_no_frigate_resume":
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
            "failed": (
                mqtt_failed
                and not (
                    allow_expected_mqtt_no_frigate_resume
                    and str((mqtt_evidence or {}).get("reason_code") or "").strip().lower()
                    == "frigate_recovery_no_frigate_resume"
                )
                if scenario in {"mqtt-no-frigate-resume", "combined"}
                else False
            ),
            "reason": (
                "mqtt_no_frigate_resume_detected"
                if mqtt_failed
                and not (
                    allow_expected_mqtt_no_frigate_resume
                    and str((mqtt_evidence or {}).get("reason_code") or "").strip().lower()
                    == "frigate_recovery_no_frigate_resume"
                )
                else None
            ),
            "evidence": mqtt_evidence,
        },
    }
    return tracks


def _evaluate_fixture_replay(
    *,
    enabled: bool,
    backfill_result: dict[str, Any] | None,
    manual_tag_result: dict[str, Any] | None,
    analysis_triggers: list[dict[str, Any]],
    min_backfill_processed: int,
    min_analysis_total_candidates: int,
    reconnect_delta: int | None,
    min_reconnect_delta: int | None,
    app_frigate_stale_seconds: float | None = None,
    max_observed_frigate_age_seconds: float | None = None,
) -> dict[str, Any]:
    if not enabled:
        return {"checked": False, "passed": True, "failure_reasons": []}

    reasons: list[str] = []
    backfill_response = (backfill_result or {}).get("response") if isinstance(backfill_result, dict) else None
    if not isinstance(backfill_response, dict):
        reasons.append("Fixture replay backfill did not run.")
        processed = 0
        errors = 0
    else:
        processed = int(backfill_response.get("processed") or 0)
        errors = int(backfill_response.get("errors") or 0)
        if processed < int(min_backfill_processed):
            reasons.append(
                f"Fixture replay backfill processed too few events ({processed} < {int(min_backfill_processed)})."
            )
        if errors > 0:
            reasons.append(f"Fixture replay backfill reported errors ({errors}).")

    manual_response = (manual_tag_result or {}).get("response") if isinstance(manual_tag_result, dict) else None
    manual_updated = int((manual_response or {}).get("updated_count") or 0) if isinstance(manual_response, dict) else 0
    if min_analysis_total_candidates > 0 and manual_updated <= 0:
        reasons.append("Fixture replay did not retag any seeded detections as Unknown Bird.")

    max_candidates = 0
    max_accepted = 0
    observed_analysis = False
    for trigger in analysis_triggers:
        if not isinstance(trigger, dict) or not trigger.get("ok"):
            continue
        response = trigger.get("response")
        if not isinstance(response, dict):
            continue
        observed_analysis = True
        max_candidates = max(max_candidates, int(response.get("total_candidates") or 0))
        max_accepted = max(max_accepted, int(response.get("accepted") or 0))
        status = str(response.get("status") or "")
        if status == "in_progress" and int(response.get("count") or 0) > 0:
            max_candidates = max(max_candidates, int(response.get("count") or 0))

    if not observed_analysis or max_candidates < int(min_analysis_total_candidates):
        reasons.append("Fixture replay analyze-unknowns did not observe any candidate work.")

    if min_reconnect_delta is not None:
        reconnect_value = int(reconnect_delta or 0)
        if reconnect_value < int(min_reconnect_delta):
            if (
                app_frigate_stale_seconds is not None
                and max_observed_frigate_age_seconds is not None
                and max_observed_frigate_age_seconds < app_frigate_stale_seconds
            ):
                reasons.append(
                    "Fixture replay did not run long enough to exercise MQTT reconnect "
                    f"(max Frigate age {max_observed_frigate_age_seconds:.1f}s < app stale threshold "
                    f"{app_frigate_stale_seconds:.1f}s)."
                )
            else:
                reasons.append(
                    f"Fixture replay MQTT reconnect growth below threshold ({reconnect_value} < {int(min_reconnect_delta)})."
                )
    else:
        reconnect_value = int(reconnect_delta or 0)

    return {
        "checked": True,
        "passed": not reasons,
        "failure_reasons": reasons,
        "backfill_processed": processed,
        "backfill_errors": errors,
        "manual_tag_updated": manual_updated,
        "analysis_max_total_candidates": max_candidates,
        "analysis_max_accepted": max_accepted,
        "reconnect_delta": reconnect_value,
        "app_frigate_stale_seconds": app_frigate_stale_seconds,
        "max_observed_frigate_age_seconds": max_observed_frigate_age_seconds,
    }


def _max_observed_frigate_age_seconds(samples: list[Any]) -> float | None:
    ages = [
        float(age)
        for age in (getattr(sample, "mqtt_frigate_age_seconds", None) for sample in samples)
        if age is not None
    ]
    return max(ages) if ages else None


def _mqtt_frigate_stale_seconds_from_health(payload: dict[str, Any]) -> float | None:
    mqtt = payload.get("mqtt") if isinstance(payload, dict) else None
    if not isinstance(mqtt, dict):
        return None
    value = mqtt.get("frigate_topic_stale_seconds")
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


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
    frigate_stats = base_soak.PublisherStats()
    birdnet_stats = base_soak.PublisherStats()
    induced_frigate_stall_at: str | None = None
    resumed_frigate_at: str | None = None
    replay_seed_events: list[dict[str, Any]] = []
    fixture_events: list[dict[str, Any]] = []
    fixture_server: _FixtureFrigateServer | None = None
    fixture_server_url: str | None = None
    backfill_result: dict[str, Any] | None = None
    manual_tag_result: dict[str, Any] | None = None

    def _handle_signal(_signum, _frame) -> None:
        base_soak._log("Received termination signal; stopping issue #33 harness.")
        stop_event.set()
        frigate_stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    frigate_threads: list[threading.Thread] = []
    birdnet_threads: list[threading.Thread] = []

    if args.frigate_load_source == "fixture":
        if not auth_token:
            parser.error("--username/--password or --auth-token is required for fixture replay backfill validation")
        if not args.fixture_image_dir:
            parser.error("--fixture-image-dir is required when --frigate-load-source fixture is enabled")
        fixture_images = _discover_fixture_images(args.fixture_image_dir)
        if not fixture_images:
            parser.error(f"No fixture images found under {args.fixture_image_dir}")
        fixture_events = _build_fixture_events(
            images=fixture_images,
            count=args.fixture_event_count,
            camera=args.frigate_camera,
            run_label=run_label,
            now=run_started_at,
        )
        clip_path = _generate_fixture_clip(
            image_path=fixture_images[0],
            output_dir=output_dir,
            seconds=args.fixture_clip_seconds,
        )
        fixture_server = _FixtureFrigateServer(
            host=args.fixture_frigate_host,
            port=args.fixture_frigate_port,
            events=fixture_events,
            clip_path=clip_path,
        )
        fixture_server_url = fixture_server.start()
        args.frigate_api_url = fixture_server_url
        replay_seed_events = fixture_events
        base_soak._log(
            "Using fixture-backed Frigate load "
            f"({len(fixture_events)} event(s), images={len(fixture_images)}, url={fixture_server_url})"
        )

    frigate_payload_factory = None
    if not args.disable_frigate_publisher:
        if args.frigate_load_source == "fixture":
            frigate_payload_factory = _build_replay_payload_factory(fixture_events)
        elif args.frigate_load_source == "replay":
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

    def _start_frigate_publishers(current_stop_event: threading.Event) -> list[threading.Thread]:
        started_threads: list[threading.Thread] = []
        for replica in _publisher_replicas(args.disable_frigate_publisher, args.frigate_publisher_replicas):
            frigate_thread = threading.Thread(
                target=base_soak._publisher_loop,
                kwargs={
                    "stop_event": current_stop_event,
                    "stats": frigate_stats,
                    "mqtt_host": args.mqtt_host,
                    "mqtt_port": args.mqtt_port,
                    "mqtt_username": args.mqtt_username,
                    "mqtt_password": args.mqtt_password,
                    "topic": args.frigate_topic,
                    "payload_factory": (
                        frigate_payload_factory
                        if args.frigate_load_source in {"replay", "fixture"}
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
                },
                daemon=True,
            )
            frigate_thread.start()
            started_threads.append(frigate_thread)
        return started_threads

    frigate_threads = _start_frigate_publishers(frigate_stop_event)

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

    if args.trigger_backfill:
        if not auth_token:
            parser.error("--trigger-backfill requires owner authentication")
        try:
            backfill_response = _trigger_backfill(
                backend_url=args.backend_url,
                token=auth_token,
                timeout_seconds=max(args.http_timeout_seconds, 120.0),
                start_date=run_started_at.strftime("%Y-%m-%d"),
                end_date=run_started_at.strftime("%Y-%m-%d"),
                cameras=[args.frigate_camera],
            )
            backfill_result = {"ok": True, "response": backfill_response}
            base_soak._write_ndjson_line(
                samples_path,
                {
                    "type": "backfill_trigger",
                    "observed_at": base_soak._now_utc().isoformat(),
                    "ok": True,
                    "response": backfill_response,
                },
            )
        except Exception as exc:
            backfill_result = {"ok": False, "error": str(exc)}
            base_soak._write_ndjson_line(
                samples_path,
                {
                    "type": "backfill_trigger",
                    "observed_at": base_soak._now_utc().isoformat(),
                    "ok": False,
                    "error": str(exc),
                },
            )

        if args.fixture_manual_tag_unknown and fixture_events:
            try:
                manual_response = _manual_tag_unknowns(
                    backend_url=args.backend_url,
                    token=auth_token,
                    timeout_seconds=max(args.http_timeout_seconds, 30.0),
                    event_ids=[str(event["id"]) for event in fixture_events],
                )
                manual_tag_result = {"ok": True, "response": manual_response}
                base_soak._write_ndjson_line(
                    samples_path,
                    {
                        "type": "fixture_manual_tag_unknown",
                        "observed_at": base_soak._now_utc().isoformat(),
                        "ok": True,
                        "response": manual_response,
                    },
                )
            except Exception as exc:
                manual_tag_result = {"ok": False, "error": str(exc)}
                base_soak._write_ndjson_line(
                    samples_path,
                    {
                        "type": "fixture_manual_tag_unknown",
                        "observed_at": base_soak._now_utc().isoformat(),
                        "ok": False,
                        "error": str(exc),
                    },
                )

    samples = []
    diagnostics_workspace_snapshots: list[dict[str, Any]] = []
    analysis_triggers: list[dict[str, Any]] = []
    health_fetch_failures = 0
    app_frigate_stale_seconds: float | None = None
    deadline = time.time() + max(1, args.duration_seconds)
    next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds if args.trigger_analysis_interval_seconds > 0 else None

    while not stop_event.is_set() and time.time() < deadline:
        tick_started = time.time()
        elapsed = tick_started - run_started_at.timestamp()
        observed_at = base_soak._now_utc()

        should_run_frigate_publishers = not args.disable_frigate_publisher and not _should_pause_frigate_publisher(
            elapsed_seconds=elapsed,
            stop_after_seconds=args.induce_frigate_stall_after_seconds,
            stall_duration_seconds=args.frigate_stall_duration_seconds,
        )
        frigate_was_running = _frigate_publishers_running(frigate_threads)
        frigate_threads, frigate_stop_event, frigate_state_changed = _set_frigate_publishers_running(
            should_run=should_run_frigate_publishers,
            threads=frigate_threads,
            stop_event=frigate_stop_event,
            start_publishers=_start_frigate_publishers,
        )
        if frigate_state_changed:
            if not should_run_frigate_publishers and frigate_was_running:
                induced_frigate_stall_at = observed_at.isoformat()
                base_soak._write_ndjson_line(
                    samples_path,
                    {
                        "type": "frigate_publisher_paused",
                        "observed_at": induced_frigate_stall_at,
                        "elapsed_seconds": round(elapsed, 1),
                    },
                )
            elif should_run_frigate_publishers and not frigate_was_running:
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
            app_frigate_stale_seconds = app_frigate_stale_seconds or _mqtt_frigate_stale_seconds_from_health(payload)
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
    if fixture_server:
        fixture_server.stop()

    evaluation = evaluate_soak_run(samples, thresholds, health_fetch_failures=health_fetch_failures)
    evaluation = _normalize_issue33_evaluation(
        evaluation,
        scenario=args.scenario,
        induced_frigate_stall=(
            induced_frigate_stall_at is not None
        ),
        samples=samples,
        induced_frigate_stall_at=induced_frigate_stall_at,
        resumed_frigate_at=resumed_frigate_at,
        birdnet_publish_stats=asdict(birdnet_stats),
        max_birdnet_active_age_seconds=thresholds.max_birdnet_active_age_seconds,
        min_stall_duration_seconds=thresholds.min_stall_duration_seconds,
        require_inference_health=True,
    )
    tracks = _evaluate_issue33_tracks(
        scenario=args.scenario,
        health_evaluation=evaluation,
        diagnostics_workspace=diagnostics_workspace_snapshots,
        run_started_at=run_started_at.isoformat(),
        allow_expected_mqtt_no_frigate_resume=(
            args.frigate_load_source == "fixture" and args.frigate_stall_duration_seconds <= 0
        ),
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
    fixture_replay_evaluation = _evaluate_fixture_replay(
        enabled=args.frigate_load_source == "fixture",
        backfill_result=backfill_result,
        manual_tag_result=manual_tag_result,
        analysis_triggers=analysis_triggers,
        min_backfill_processed=args.min_backfill_processed,
        min_analysis_total_candidates=args.min_analysis_total_candidates,
        reconnect_delta=evaluation.get("topic_liveness_reconnects_delta"),
        min_reconnect_delta=thresholds.min_topic_liveness_reconnects_delta,
        app_frigate_stale_seconds=app_frigate_stale_seconds,
        max_observed_frigate_age_seconds=_max_observed_frigate_age_seconds(samples),
    )
    if not fixture_replay_evaluation["passed"]:
        merged_reasons = list(evaluation.get("failure_reasons") or [])
        for reason in fixture_replay_evaluation.get("failure_reasons") or []:
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
            "fixture_image_dir": args.fixture_image_dir,
            "fixture_event_count": args.fixture_event_count,
            "fixture_frigate_url": fixture_server_url,
            "trigger_backfill": args.trigger_backfill,
            "fixture_manual_tag_unknown": args.fixture_manual_tag_unknown,
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
        "backfill": backfill_result,
        "manual_tag_unknown": manual_tag_result,
        "induced_frigate_stall_at": induced_frigate_stall_at,
        "resumed_frigate_at": resumed_frigate_at,
        "replay": {
            "seed_count": len(replay_seed_events),
            "seed_event_ids": [str(event.get("id")) for event in replay_seed_events if event.get("id")],
            "seed_cameras": sorted({str(event.get("camera")) for event in replay_seed_events if event.get("camera")}),
        },
        "evaluation": evaluation,
        "fixture_replay_evaluation": fixture_replay_evaluation,
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
