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
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.utils.issue22_soak_harness import (  # noqa: E402
    SoakSample,
    SoakThresholds,
    evaluate_soak_run,
    sample_from_health_payload,
)

try:
    import paho.mqtt.client as mqtt
except ImportError as exc:  # pragma: no cover - exercised in runtime, not unit tests.
    raise SystemExit(
        "Missing dependency: paho-mqtt. Run this script with backend venv, e.g. "
        "`/config/workspace/YA-WAMF/backend/venv/bin/python scripts/run_issue22_soak.py ...`"
    ) from exc


@dataclass
class PublisherStats:
    published: int = 0
    publish_failures: int = 0
    connect_failures: int = 0
    last_error: str | None = None


MQTT_CONNECT_TIMEOUT_SECONDS = 5.0
MQTT_PUBLISH_TIMEOUT_SECONDS = 5.0


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _log(message: str) -> None:
    print(f"[{_now_utc().isoformat()}] {message}", flush=True)


def _request_json(
    method: str,
    url: str,
    token: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(url=url, method=method.upper(), headers=headers)
    with urlopen(request, timeout=timeout_seconds) as response:
        payload = response.read()
    return json.loads(payload.decode("utf-8"))


def _trigger_unknown_analysis(
    backend_url: str,
    analysis_path: str,
    token: str | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    url = urljoin(f"{backend_url.rstrip('/')}/", analysis_path.lstrip("/"))
    return _request_json("POST", url, token, timeout_seconds)


def _fetch_health(backend_url: str, health_path: str, token: str | None, timeout_seconds: float) -> dict[str, Any]:
    url = urljoin(f"{backend_url.rstrip('/')}/", health_path.lstrip("/"))
    return _request_json("GET", url, token, timeout_seconds)


def _build_frigate_payload(event_id: str, event_type: str, false_positive: bool = False) -> str:
    return json.dumps(
        {
            "type": event_type,
            "after": {
                "id": event_id,
                "camera": "soak_cam",
                "label": "bird",
                "start_time": time.time(),
                "false_positive": false_positive,
                "top_score": 0.99,
                "sub_label": "Parus major",
            },
        },
        separators=(",", ":"),
    )


def _build_birdnet_payload(sequence: int) -> str:
    source = f"soak-source-{sequence % 3}"
    return json.dumps(
        {
            "comName": "Great Tit",
            "ScientificName": "Parus major",
            "score": 0.98,
            "timestamp": time.time(),
            "nm": source,
            "Source": {"displayName": source},
        },
        separators=(",", ":"),
    )


def _connect_mqtt_client(client, *, mqtt_host: str, mqtt_port: int, timeout_seconds: float) -> None:
    connected = threading.Event()

    def _on_connect(_client, _userdata, _flags, rc, _properties=None):
        if rc == 0:
            connected.set()

    client.on_connect = _on_connect
    client.connect(mqtt_host, mqtt_port, keepalive=30)
    client.loop_start()
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if connected.wait(0.05):
            return
        is_connected = getattr(client, "is_connected", None)
        if callable(is_connected) and is_connected():
            return
    raise TimeoutError(f"MQTT connect timed out after {timeout_seconds}s")


def _publish_message(client, *, topic: str, payload: str, timeout_seconds: float) -> None:
    info = client.publish(topic, payload=payload, qos=1, retain=False)
    if info.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(f"publish rc={info.rc}")

    if not hasattr(info, "is_published"):
        return

    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        if info.is_published():
            return
        time.sleep(0.01)
    raise TimeoutError(f"MQTT publish timed out after {timeout_seconds}s")


def _build_mosquitto_pub_command(
    *,
    container_name: str,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    topic: str,
    payload: str,
) -> list[str]:
    command = [
        "docker",
        "exec",
        container_name,
        "mosquitto_pub",
        "-h",
        mqtt_host,
        "-p",
        str(mqtt_port),
    ]
    if mqtt_username:
        command.extend(["-u", mqtt_username, "-P", mqtt_password or ""])
    command.extend(["-t", topic, "-m", payload])
    return command


def _publish_message_via_container(
    *,
    container_name: str,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    topic: str,
    payload: str,
    timeout_seconds: float,
) -> None:
    command = _build_mosquitto_pub_command(
        container_name=container_name,
        mqtt_host=mqtt_host,
        mqtt_port=mqtt_port,
        mqtt_username=mqtt_username,
        mqtt_password=mqtt_password,
        topic=topic,
        payload=payload,
    )
    subprocess.run(command, check=True, timeout=timeout_seconds, capture_output=True, text=True)


def _publisher_loop(
    *,
    stop_event: threading.Event,
    stats: PublisherStats,
    mqtt_host: str,
    mqtt_port: int,
    mqtt_username: str | None,
    mqtt_password: str | None,
    topic: str,
    payload_factory,
    interval_seconds: float,
    client_id_prefix: str,
    publish_container: str | None = None,
) -> None:
    if publish_container:
        sequence = 0
        while not stop_event.is_set():
            payload = payload_factory(sequence)
            sequence += 1
            try:
                _publish_message_via_container(
                    container_name=publish_container,
                    mqtt_host="127.0.0.1",
                    mqtt_port=mqtt_port,
                    mqtt_username=mqtt_username,
                    mqtt_password=mqtt_password,
                    topic=topic,
                    payload=payload,
                    timeout_seconds=MQTT_PUBLISH_TIMEOUT_SECONDS,
                )
                stats.published += 1
                time.sleep(interval_seconds)
            except Exception as exc:  # pragma: no cover - runtime subprocess path
                stats.publish_failures += 1
                stats.last_error = str(exc)
                time.sleep(min(interval_seconds, 2.0))
        return

    client_id = f"{client_id_prefix}-{uuid.uuid4().hex[:8]}"
    client = mqtt.Client(client_id=client_id, clean_session=True)
    if mqtt_username:
        client.username_pw_set(username=mqtt_username, password=mqtt_password or "")

    connected = False
    loop_started = False
    sequence = 0

    try:
        while not stop_event.is_set():
            if not connected:
                try:
                    _connect_mqtt_client(
                        client,
                        mqtt_host=mqtt_host,
                        mqtt_port=mqtt_port,
                        timeout_seconds=MQTT_CONNECT_TIMEOUT_SECONDS,
                    )
                    loop_started = True
                    connected = True
                except Exception as exc:  # pragma: no cover - runtime networking path
                    stats.connect_failures += 1
                    stats.last_error = str(exc)
                    time.sleep(min(interval_seconds, 2.0))
                    continue

            payload = payload_factory(sequence)
            sequence += 1
            try:
                _publish_message(
                    client,
                    topic=topic,
                    payload=payload,
                    timeout_seconds=MQTT_PUBLISH_TIMEOUT_SECONDS,
                )
                stats.published += 1
                time.sleep(interval_seconds)
            except Exception as exc:  # pragma: no cover - runtime networking path
                stats.publish_failures += 1
                stats.last_error = str(exc)
                connected = False
                time.sleep(min(interval_seconds, 2.0))
    finally:
        if loop_started:
            client.loop_stop()
        try:
            client.disconnect()
        except Exception:  # pragma: no cover - defensive shutdown path
            pass


def _write_ndjson_line(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, separators=(",", ":")))
        handle.write("\n")


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run issue #22 soak validation against YA-WAMF health + MQTT liveness metrics."
    )
    parser.add_argument("--backend-url", default=os.getenv("SOAK_BACKEND_URL", "http://127.0.0.1:8946"))
    parser.add_argument("--health-path", default="/health")
    parser.add_argument("--analysis-path", default="/api/maintenance/analyze-unknowns")
    parser.add_argument("--auth-token", default=os.getenv("SOAK_AUTH_TOKEN"))
    parser.add_argument("--duration-seconds", type=int, default=1800)
    parser.add_argument("--poll-interval-seconds", type=float, default=5.0)
    parser.add_argument("--http-timeout-seconds", type=float, default=5.0)
    parser.add_argument("--trigger-analysis-interval-seconds", type=float, default=0.0)
    parser.add_argument("--mqtt-host", default=os.getenv("SOAK_MQTT_HOST", os.getenv("MQTT_SERVER", "127.0.0.1")))
    parser.add_argument("--mqtt-port", type=int, default=int(os.getenv("SOAK_MQTT_PORT", os.getenv("MQTT_PORT", "1883"))))
    parser.add_argument("--mqtt-username", default=os.getenv("SOAK_MQTT_USERNAME", os.getenv("MQTT_USERNAME")))
    parser.add_argument("--mqtt-password", default=os.getenv("SOAK_MQTT_PASSWORD", os.getenv("MQTT_PASSWORD")))
    parser.add_argument("--mqtt-publish-container", default=os.getenv("SOAK_MQTT_PUBLISH_CONTAINER", ""))
    parser.add_argument("--frigate-topic", default=os.getenv("SOAK_FRIGATE_TOPIC", "frigate/events"))
    parser.add_argument("--birdnet-topic", default=os.getenv("SOAK_BIRDNET_TOPIC", "birdnet/text"))
    parser.add_argument("--frigate-event-type", choices=["update", "new", "end"], default="update")
    parser.add_argument("--frigate-false-positive", action="store_true")
    parser.add_argument("--frigate-publish-interval-seconds", type=float, default=1.0)
    parser.add_argument("--birdnet-publish-interval-seconds", type=float, default=1.0)
    parser.add_argument("--output-dir", default="")

    parser.add_argument("--min-samples", type=int, default=30)
    parser.add_argument("--max-health-fetch-failures", type=int, default=3)
    parser.add_argument("--min-frigate-delta", type=int, default=30)
    parser.add_argument("--min-birdnet-delta", type=int, default=30)
    parser.add_argument("--max-degraded-ratio", type=float, default=0.20)
    parser.add_argument("--max-pressure-level", choices=["normal", "elevated", "high", "critical"], default="high")
    parser.add_argument("--frigate-stall-age-seconds", type=float, default=120.0)
    parser.add_argument("--max-birdnet-active-age-seconds", type=float, default=20.0)
    parser.add_argument("--min-stall-duration-seconds", type=float, default=60.0)
    return parser


def main() -> int:
    parser = _build_arg_parser()
    args = parser.parse_args()

    run_started_at = _now_utc()
    run_label = run_started_at.strftime("%Y%m%d-%H%M%S")
    output_dir = Path(args.output_dir) if args.output_dir else REPO_ROOT / "tmp" / "issue22-soak" / run_label
    output_dir.mkdir(parents=True, exist_ok=True)
    samples_path = output_dir / "samples.ndjson"
    summary_path = output_dir / "summary.json"

    thresholds = SoakThresholds(
        min_samples=args.min_samples,
        min_frigate_messages_delta=args.min_frigate_delta,
        min_birdnet_messages_delta=args.min_birdnet_delta,
        max_degraded_ratio=args.max_degraded_ratio,
        max_pressure_level=args.max_pressure_level,
        frigate_stall_age_seconds=args.frigate_stall_age_seconds,
        max_birdnet_active_age_seconds=args.max_birdnet_active_age_seconds,
        min_stall_duration_seconds=args.min_stall_duration_seconds,
        max_health_fetch_failures=args.max_health_fetch_failures,
    )

    _log(f"Starting issue #22 soak harness for {args.duration_seconds}s")
    _log(f"Artifacts: {output_dir}")

    stop_event = threading.Event()
    frigate_stats = PublisherStats()
    birdnet_stats = PublisherStats()

    def _handle_signal(_signum, _frame) -> None:
        _log("Received termination signal; stopping soak run.")
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    frigate_thread = threading.Thread(
        target=_publisher_loop,
        kwargs={
            "stop_event": stop_event,
            "stats": frigate_stats,
            "mqtt_host": args.mqtt_host,
            "mqtt_port": args.mqtt_port,
            "mqtt_username": args.mqtt_username,
            "mqtt_password": args.mqtt_password,
            "topic": args.frigate_topic,
            "payload_factory": lambda seq: _build_frigate_payload(
                event_id=f"soak-{run_label}-{seq}",
                event_type=args.frigate_event_type,
                false_positive=args.frigate_false_positive,
            ),
            "interval_seconds": max(0.05, args.frigate_publish_interval_seconds),
            "client_id_prefix": "issue22-frigate",
            "publish_container": args.mqtt_publish_container or None,
        },
        daemon=True,
    )
    birdnet_thread = threading.Thread(
        target=_publisher_loop,
        kwargs={
            "stop_event": stop_event,
            "stats": birdnet_stats,
            "mqtt_host": args.mqtt_host,
            "mqtt_port": args.mqtt_port,
            "mqtt_username": args.mqtt_username,
            "mqtt_password": args.mqtt_password,
            "topic": args.birdnet_topic,
            "payload_factory": _build_birdnet_payload,
            "interval_seconds": max(0.05, args.birdnet_publish_interval_seconds),
            "client_id_prefix": "issue22-birdnet",
            "publish_container": args.mqtt_publish_container or None,
        },
        daemon=True,
    )

    frigate_thread.start()
    birdnet_thread.start()

    samples: list[SoakSample] = []
    analysis_triggers: list[dict[str, Any]] = []
    health_fetch_failures = 0
    deadline = time.time() + max(1, args.duration_seconds)
    next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds if args.trigger_analysis_interval_seconds > 0 else None

    while not stop_event.is_set() and time.time() < deadline:
        tick_started = time.time()
        observed_at = _now_utc()
        try:
            payload = _fetch_health(
                backend_url=args.backend_url,
                health_path=args.health_path,
                token=args.auth_token,
                timeout_seconds=args.http_timeout_seconds,
            )
            sample = sample_from_health_payload(payload, observed_at=observed_at)
            samples.append(sample)
            _write_ndjson_line(samples_path, {"type": "health_sample", **sample.to_json()})
        except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
            health_fetch_failures += 1
            _write_ndjson_line(
                samples_path,
                {
                    "type": "health_fetch_error",
                    "observed_at": observed_at.astimezone(timezone.utc).isoformat(),
                    "error": str(exc),
                },
            )

        if next_analysis_trigger is not None and time.time() >= next_analysis_trigger:
            trigger_time = _now_utc()
            trigger_result: dict[str, Any]
            try:
                response = _trigger_unknown_analysis(
                    backend_url=args.backend_url,
                    analysis_path=args.analysis_path,
                    token=args.auth_token,
                    timeout_seconds=args.http_timeout_seconds,
                )
                trigger_result = {
                    "observed_at": trigger_time.astimezone(timezone.utc).isoformat(),
                    "ok": True,
                    "response": response,
                }
            except Exception as exc:  # pragma: no cover - integration path
                trigger_result = {
                    "observed_at": trigger_time.astimezone(timezone.utc).isoformat(),
                    "ok": False,
                    "error": str(exc),
                }
            analysis_triggers.append(trigger_result)
            _write_ndjson_line(samples_path, {"type": "analysis_trigger", **trigger_result})
            next_analysis_trigger = time.time() + args.trigger_analysis_interval_seconds

        elapsed = time.time() - tick_started
        sleep_for = max(0.0, args.poll_interval_seconds - elapsed)
        time.sleep(sleep_for)

    stop_event.set()
    frigate_thread.join(timeout=5.0)
    birdnet_thread.join(timeout=5.0)

    evaluation = evaluate_soak_run(samples, thresholds, health_fetch_failures=health_fetch_failures)
    run_finished_at = _now_utc()
    duration_actual_seconds = max(0.0, (run_finished_at - run_started_at).total_seconds())

    summary = {
        "issue": 22,
        "status": "pass" if evaluation["passed"] else "fail",
        "run_started_at": run_started_at.astimezone(timezone.utc).isoformat(),
        "run_finished_at": run_finished_at.astimezone(timezone.utc).isoformat(),
        "duration_seconds": round(duration_actual_seconds, 1),
        "config": {
            "backend_url": args.backend_url,
            "health_path": args.health_path,
            "analysis_path": args.analysis_path,
            "duration_seconds": args.duration_seconds,
            "poll_interval_seconds": args.poll_interval_seconds,
            "trigger_analysis_interval_seconds": args.trigger_analysis_interval_seconds,
            "mqtt_host": args.mqtt_host,
            "mqtt_port": args.mqtt_port,
            "mqtt_publish_container": args.mqtt_publish_container,
            "frigate_topic": args.frigate_topic,
            "birdnet_topic": args.birdnet_topic,
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
        "evaluation": evaluation,
        "artifacts": {
            "samples_ndjson": str(samples_path),
            "summary_json": str(summary_path),
        },
        "note": "Harness collects validation evidence only. It does not close GitHub issues.",
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    _log(f"Completed soak run: {summary['status'].upper()}")
    _log(f"Summary written to {summary_path}")

    if not evaluation["passed"]:
        for reason in evaluation["failure_reasons"]:
            _log(f"FAILURE: {reason}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
