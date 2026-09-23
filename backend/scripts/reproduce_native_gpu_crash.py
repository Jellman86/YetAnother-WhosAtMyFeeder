"""Local-only OpenVINO crash probe, independent of application state and services.

Synthetic inputs test runtime stability, not classifier accuracy. Each repeat has
a bounded disposable process. Keep the output private and review before sharing.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time
from typing import Any


def write_report(path: Path, report: dict[str, Any]) -> None:
    temporary = path.with_suffix(".tmp")
    with temporary.open("w") as stream:
        json.dump(report, stream, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def child_environment(root: Path) -> dict[str, str]:
    environment = {key: os.environ[key] for key in ("PATH", "LD_LIBRARY_PATH", "LANG", "LC_ALL") if key in os.environ}
    environment.update(
        HOME=str(root),
        XDG_CACHE_HOME=str(root / "driver-cache"),
        PYTHONUNBUFFERED="1",
        OMP_NUM_THREADS="2",
        OPENBLAS_NUM_THREADS="2",
    )
    return environment


def classify_outcome(code: int | None, report: dict[str, Any], *, timed_out: bool) -> str:
    if timed_out:
        return "timeout"
    if code in {
        -int(getattr(signal, name))
        for name in ("SIGSEGV", "SIGABRT", "SIGBUS", "SIGILL", "SIGFPE")
        if hasattr(signal, name)
    }:
        return "native_crash"
    if code != 0:
        return "failed"
    return "passed" if report.get("phase") == "complete" and report.get("ok") is True else "incomplete"


def run_child(command: list[str], root: Path, report_path: Path, *, timeout: float) -> dict[str, Any]:
    started = time.monotonic()
    timed_out = False
    with (root / "process.log").open("wb") as log:
        process = subprocess.Popen(command, env=child_environment(root), cwd=root, stdout=log, stderr=log)
        try:
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            process.kill()
            # A kernel-level uninterruptible wait must not hang the diagnostic
            # parent forever or allow it to start another model alongside this one.
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                return {"outcome": "cleanup_failed", "pid": process.pid, "exit_code": None}
    try:
        report = json.loads(report_path.read_text())
        if not isinstance(report, dict):
            report = {}
    except (OSError, ValueError):
        report = {}
    return {
        "outcome": classify_outcome(process.returncode, report, timed_out=timed_out),
        "exit_code": process.returncode,
        "seconds": round(time.monotonic() - started, 3),
        "report": report,
    }


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(args: argparse.Namespace) -> None:
    import resource

    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    report: dict[str, Any] = {"ok": False, "phase": "import", "iterations_completed": 0}

    def phase(name: str) -> None:
        report["phase"] = name
        write_report(args.report, report)

    phase("import")
    try:
        import numpy as np
        import openvino as ov

        report["openvino"] = ov.__version__
        report["numpy"] = np.__version__
        phase("device_discovery")
        core = ov.Core()
        report["available_devices"] = core.available_devices
        report["device"] = args.device
        report["device_name"] = str(core.get_property(args.device, "FULL_DEVICE_NAME"))
        phase("read_model")
        model = core.read_model(str(args.model))
        if args.shape:
            if len(model.inputs) != 1:
                raise ValueError("--shape supports single-input models only")
            model.reshape({model.input(0): [int(value) for value in args.shape.split(",")]})
        if any(port.partial_shape.is_dynamic for port in model.inputs):
            raise ValueError("Dynamic input: supply the exact static --shape for this artifact")
        report["inputs"] = [{"shape": list(port.shape), "type": str(port.element_type)} for port in model.inputs]
        properties = {"CACHE_DIR": str(args.cache_dir)} if args.cache_dir else {"CACHE_DIR": ""}
        report["compile_properties"] = {"cache_enabled": bool(args.cache_dir)}
        phase("compile")
        compiled = core.compile_model(model, args.device, properties)
        report["execution_devices"] = list(compiled.get_property("EXECUTION_DEVICES"))
        if not report["execution_devices"] or not all(
            str(device).split(".")[0] == args.device.split(".")[0] for device in report["execution_devices"]
        ):
            raise RuntimeError("Unexpected device fallback")
        rng = np.random.default_rng(42)
        inputs = {}
        for index, port in enumerate(compiled.inputs):
            dtype = port.element_type.to_dtype()
            shape = tuple(port.shape)
            if math.prod(shape) > 16_000_000:
                raise ValueError("Input exceeds diagnostic allocation bound")
            inputs[index] = rng.uniform(-1, 1, size=shape).astype(dtype)
        request = compiled.create_infer_request()
        for index in range(args.iterations):
            phase("inference")
            outputs = request.infer(inputs)
            if not outputs or any(not value.size or not np.isfinite(value).all() for value in outputs.values()):
                raise ValueError("Empty or non-finite inference output")
            report["iterations_completed"] = index + 1
        report["outputs"] = [
            {"shape": list(value.shape), "sha256": hashlib.sha256(value.tobytes()).hexdigest()}
            for value in outputs.values()
        ]
        phase("cleanup")
        del outputs, request, compiled, model, core
        report["ok"] = True
        phase("complete")
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        write_report(args.report, report)
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--device", choices=("CPU", "GPU", "NPU"), default="GPU")
    parser.add_argument("--shape", help="Explicit comma-separated static shape for a single-input model")
    parser.add_argument("--repeat", type=int, default=3)
    parser.add_argument("--iterations", type=int, default=10)
    parser.add_argument("--timeout", type=float, default=240)
    parser.add_argument("--cache", choices=("cold", "warm", "off"), default="cold")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--child", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--report", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--cache-dir", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if not 1 <= args.repeat <= 100 or not 1 <= args.iterations <= 10000 or not 0 < args.timeout <= 3600:
        parser.error("repeat 1..100, iterations 1..10000 and timeout (0,3600] required")
    args.model = args.model.resolve(strict=True)
    if args.child:
        probe(args)
        return 0
    if args.output is None:
        parser.error("--output must name a new private directory")
    root = args.output.resolve()
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    artifacts = [
        args.model,
        *[path for path in (Path(f"{args.model}.data"), args.model.with_suffix(".bin")) if path.is_file()],
    ]
    packages = {}
    for package in ("openvino", "numpy"):
        try:
            packages[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            packages[package] = "not installed"
    summary: dict[str, Any] = {
        "synthetic_inputs": True,
        "device": args.device,
        "cache": args.cache,
        "python": platform.python_version(),
        "kernel": platform.release(),
        "machine": platform.machine(),
        "packages": packages,
        "artifacts": {path.name: file_digest(path) for path in artifacts},
        "runs": [],
    }
    for index in range(args.repeat):
        run_root = root / f"run-{index + 1}"
        run_root.mkdir(mode=0o700)
        report = run_root / "report.json"
        command = [
            sys.executable,
            str(Path(__file__).resolve()),
            "--child",
            "--model",
            str(args.model),
            "--device",
            args.device,
            "--iterations",
            str(args.iterations),
            "--report",
            str(report),
        ]
        if args.shape:
            command.extend(["--shape", args.shape])
        if args.cache != "off":
            cache = root / "warm-cache" if args.cache == "warm" else run_root / "cold-cache"
            cache.mkdir(exist_ok=True)
            command.extend(["--cache-dir", str(cache)])
        summary["runs"].append(run_child(command, run_root, report, timeout=args.timeout))
        summary["ok"] = all(run["outcome"] == "passed" for run in summary["runs"])
        write_report(root / "summary.json", summary)
        if summary["runs"][-1]["outcome"] == "cleanup_failed":
            break
    print(
        json.dumps({"ok": summary["ok"], "outcomes": [run["outcome"] for run in summary["runs"]], "output": str(root)})
    )
    return 0 if summary["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
