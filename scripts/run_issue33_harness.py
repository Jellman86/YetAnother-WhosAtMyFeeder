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
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError

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
    parser.add_argument("--backend-url", default=os.getenv("SOAK_BACKEND_URL", "http://127.0.0.1:8946"))
    parser.add_argument("--health-path", default="/health")
    parser.add_argument("--analysis-path", default="/api/maintenance/analyze-unknowns")
    parser.add_argument("--auth-token", default=os.getenv("SOAK_AUTH_TOKEN"))
    parser.add_argument("--duration-seconds", type=int, default=900)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--http-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--trigger-analysis-interval-seconds", type=float, default=120.0)
    parser.add_argument("--induce-frigate-stall-after-seconds", type=float, default=180.0)
    parser.add_argument("--mqtt-host", default=os.getenv("SOAK_MQTT_HOST", os.getenv("MQTT_SERVER", "127.0.0.1")))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("SOAK_MQTT_PORT", os.getenv("MQTT_PORT", "1883"))))
    parser.add_argument("--mqtt-username", default=os.getenv("SOAK_MQTT_USERNAME", os.getenv("MQTT_USERNAME")))
    parser.add_argument("--mqtt-password", default=os.getenv("SOAK_MQTT_PASSWORD", os.getenv("MQTT_PASSWORD")))
    parser.add_argument("--mqtt-publish-container", default=os.getenv("SOAK_MQTT_PUBLISH_CONTAINER", ""))
    parser.add_argument("--frigate-topic", default=os.getenv("SOAK_FRIGATE_TOPIC", "frigate/events"))
    parser.add_argument("--birdnet-topic", default=os.getenv("SOAK_BIRDNET_TOPIC", "birdnet/text"))
    parser.add_argument("--disable-frigate-publisher", action="store_true")
    parser.add_argument("--disable-birdnet-publisher", action="store_true")
    parser.add_argument("--frigate-event-type", choices=["update", "new", "end"], default="update")
    parser.add_argument("--frigate-false-positive", action="store_true")
    parser.add_argument("--frigate-publish-interval-seconds", type=float, default=1.0)
    parser.add_argument("--birdnet-publish-interval-seconds", type=float, default=1.0)
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


def _normalize_issue33_evaluation(
    evaluation: dict[str, Any],
    *,
    induced_frigate_stall: bool,
) -> dict[str, Any]:
    if not induced_frigate_stall:
        return evaluation

    filtered_reasons = [
        reason
        for reason in list(evaluation.get("failure_reasons") or [])
        if not (
            reason.startswith("Frigate topic message growth below threshold ")
            or reason.startswith("Frigate stream stalled while BirdNET remained active ")
        )
    ]

    normalized = dict(evaluation)
    normalized["failure_reasons"] = filtered_reasons
    normalized["passed"] = len(filtered_reasons) == 0
    return normalized


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()
    thresholds = _build_thresholds(args)

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

    def _handle_signal(_signum, _frame) -> None:
        base_soak._log("Received termination signal; stopping issue #33 harness.")
        stop_event.set()
        frigate_stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    frigate_thread: threading.Thread | None = None
    birdnet_thread: threading.Thread | None = None

    if not args.disable_frigate_publisher:
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
                "payload_factory": lambda seq: base_soak._build_frigate_payload(
                    event_id=f"issue33-{run_label}-{seq}",
                    event_type=args.frigate_event_type,
                    false_positive=args.frigate_false_positive,
                ),
                "interval_seconds": max(0.05, args.frigate_publish_interval_seconds),
                "client_id_prefix": "issue33-frigate",
                "publish_container": args.mqtt_publish_container or None,
            },
            daemon=True,
        )
        frigate_thread.start()

    if not args.disable_birdnet_publisher:
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
                "payload_factory": base_soak._build_birdnet_payload,
                "interval_seconds": max(0.05, args.birdnet_publish_interval_seconds),
                "client_id_prefix": "issue33-birdnet",
                "publish_container": args.mqtt_publish_container or None,
            },
            daemon=True,
        )
        birdnet_thread.start()

    samples = []
    analysis_triggers: list[dict[str, Any]] = []
    health_fetch_failures = 0
    deadline = time.time() + max(1, args.duration_seconds)
    next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds if args.trigger_analysis_interval_seconds > 0 else None

    while not stop_event.is_set() and time.time() < deadline:
        tick_started = time.time()
        elapsed = tick_started - run_started_at.timestamp()
        observed_at = base_soak._now_utc()

        if (
            induced_frigate_stall_at is None
            and not args.disable_frigate_publisher
            and _should_stop_frigate_publisher(
                elapsed_seconds=elapsed,
                stop_after_seconds=args.induce_frigate_stall_after_seconds,
            )
        ):
            frigate_stop_event.set()
            induced_frigate_stall_at = observed_at.isoformat()
            base_soak._write_ndjson_line(
                samples_path,
                {
                    "type": "frigate_publisher_stopped",
                    "observed_at": induced_frigate_stall_at,
                    "elapsed_seconds": round(elapsed, 1),
                },
            )

        try:
            payload = base_soak._fetch_health(
                backend_url=args.backend_url,
                health_path=args.health_path,
                token=args.auth_token,
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

        if next_analysis_trigger is not None and time.time() >= next_analysis_trigger:
            trigger_time = base_soak._now_utc()
            try:
                response = base_soak._trigger_unknown_analysis(
                    backend_url=args.backend_url,
                    analysis_path=args.analysis_path,
                    token=args.auth_token,
                    timeout_seconds=args.http_timeout_seconds,
                )
                trigger_result = {
                    "observed_at": trigger_time.isoformat(),
                    "ok": True,
                    "response": response,
                }
            except Exception as exc:  # pragma: no cover - integration path
                trigger_result = {
                    "observed_at": trigger_time.isoformat(),
                    "ok": False,
                    "error": str(exc),
                }
            analysis_triggers.append(trigger_result)
            base_soak._write_ndjson_line(samples_path, {"type": "analysis_trigger", **trigger_result})
            next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds

        time.sleep(max(0.0, args.poll_interval_seconds - (time.time() - tick_started)))

    stop_event.set()
    frigate_stop_event.set()
    if frigate_thread is not None:
        frigate_thread.join(timeout=5.0)
    if birdnet_thread is not None:
        birdnet_thread.join(timeout=5.0)

    evaluation = evaluate_soak_run(samples, thresholds, health_fetch_failures=health_fetch_failures)
    evaluation = _normalize_issue33_evaluation(
        evaluation,
        induced_frigate_stall=(
            induced_frigate_stall_at is not None
        ),
    )
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
            "health_path": args.health_path,
            "analysis_path": args.analysis_path,
            "duration_seconds": args.duration_seconds,
            "poll_interval_seconds": args.poll_interval_seconds,
            "trigger_analysis_interval_seconds": args.trigger_analysis_interval_seconds,
            "induce_frigate_stall_after_seconds": args.induce_frigate_stall_after_seconds,
            "mqtt_host": args.mqtt_host,
            "mqtt_port": args.mqtt_port,
            "mqtt_publish_container": args.mqtt_publish_container,
            "frigate_topic": args.frigate_topic,
            "birdnet_topic": args.birdnet_topic,
            "disable_frigate_publisher": args.disable_frigate_publisher,
            "disable_birdnet_publisher": args.disable_birdnet_publisher,
            "frigate_event_type": args.frigate_event_type,
            "frigate_false_positive": args.frigate_false_positive,
            "frigate_publish_interval_seconds": args.frigate_publish_interval_seconds,
            "birdnet_publish_interval_seconds": args.birdnet_publish_interval_seconds,
            "thresholds": asdict(thresholds),
        },
        "publishers": {
            "frigate": asdict(frigate_stats),
            "birdnet": asdict(birdnet_stats),
        },
        "analysis_triggers": analysis_triggers,
        "induced_frigate_stall_at": induced_frigate_stall_at,
        "evaluation": evaluation,
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
