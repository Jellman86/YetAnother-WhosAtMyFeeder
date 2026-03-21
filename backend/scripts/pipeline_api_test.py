"""External pipeline test runner for YA-WAMF.

Exercises the live container's classification API against labeled bird images
and synthetic rejection cases. Reports accuracy, confidence, inference timing,
and per-model diagnostics so you can see exactly which models are working well
and which are not — with GPU backing if the container has it.

Prerequisites:
    python scripts/download_test_fixtures.py   # fetch iNaturalist images once

Usage:
    # Test active model against all fixture images
    python scripts/pipeline_api_test.py --base_url http://localhost:8946

    # Test with API key auth
    python scripts/pipeline_api_test.py --base_url http://localhost:8946 --api_key SECRET

    # Test only specific cases
    python scripts/pipeline_api_test.py --base_url http://localhost:8946 --cases house_sparrow,blue_jay

    # Verbose: show per-image predictions
    python scripts/pipeline_api_test.py --base_url http://localhost:8946 --verbose

    # Write JSON report
    python scripts/pipeline_api_test.py --base_url http://localhost:8946 --output report.json

    # Cycle through all installed models (activates each in turn, tests, restores)
    python scripts/pipeline_api_test.py --base_url http://localhost:8946 --all_models
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_SCRIPT_DIR = Path(__file__).resolve().parent
_BACKEND_DIR = _SCRIPT_DIR.parent
_MANIFEST_PATH = _BACKEND_DIR / "tests" / "fixtures" / "bird_image_manifest.json"
_IMAGES_DIR = _BACKEND_DIR / "tests" / "fixtures" / "bird_images"
_DOWNLOADED_PATH = _IMAGES_DIR / "downloaded.json"


# ---------------------------------------------------------------------------
# ANSI colour helpers
# ---------------------------------------------------------------------------

_RESET = "\033[0m"
_GREEN = "\033[92m"
_RED = "\033[91m"
_YELLOW = "\033[93m"
_CYAN = "\033[96m"
_BOLD = "\033[1m"
_DIM = "\033[2m"


def _green(s: str) -> str: return f"{_GREEN}{s}{_RESET}"
def _red(s: str) -> str: return f"{_RED}{s}{_RESET}"
def _yellow(s: str) -> str: return f"{_YELLOW}{s}{_RESET}"
def _cyan(s: str) -> str: return f"{_CYAN}{s}{_RESET}"
def _bold(s: str) -> str: return f"{_BOLD}{s}{_RESET}"
def _dim(s: str) -> str: return f"{_DIM}{s}{_RESET}"


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

class APIClient:
    def __init__(self, base_url: str, api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["X-API-Key"] = api_key

    def _request(self, method: str, path: str, data: bytes | None = None,
                 content_type: str | None = None) -> dict:
        url = f"{self.base_url}{path}"
        headers = dict(self._headers)
        if content_type:
            headers["Content-Type"] = content_type
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")
            raise RuntimeError(f"HTTP {e.code} from {url}: {body[:300]}") from e

    def get(self, path: str) -> dict:
        return self._request("GET", path)

    def post_multipart(self, path: str, filename: str, image_bytes: bytes) -> dict:
        """POST a file upload using multipart/form-data."""
        boundary = "----YAWAMFTestBoundary7MA4YWxkTrZu0gW"
        body = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()
        return self._request(
            "POST", path, data=body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )

    def post_json(self, path: str, payload: dict) -> dict:
        return self._request(
            "POST", path, data=json.dumps(payload).encode(),
            content_type="application/json",
        )


# ---------------------------------------------------------------------------
# Label matching
# ---------------------------------------------------------------------------

def _normalise(label: str) -> str:
    return label.lower().replace("_", " ").replace("-", " ").strip()


def _matches_acceptable(predicted_label: str, acceptable: list[str]) -> bool:
    pred_norm = _normalise(predicted_label)
    for acc in acceptable:
        acc_norm = _normalise(acc)
        if acc_norm in pred_norm or pred_norm in acc_norm:
            return True
    return False


def _find_match_rank(predictions: list[dict], acceptable: list[str]) -> int | None:
    """Return 1-based rank of first matching prediction, or None."""
    for i, p in enumerate(predictions):
        if _matches_acceptable(p.get("label", ""), acceptable):
            return i + 1
    return None


# ---------------------------------------------------------------------------
# Synthetic image generation
# ---------------------------------------------------------------------------

def _make_synthetic_image(kind: str, size: int = 224) -> bytes:
    """Return JPEG bytes for a synthetic test image."""
    try:
        from PIL import Image
        import io
        import numpy as np

        if kind == "white":
            arr = np.full((size, size, 3), 255, dtype=np.uint8)
        elif kind == "noise":
            rng = np.random.default_rng(42)
            arr = rng.integers(0, 255, (size, size, 3), dtype=np.uint8)
        elif kind == "gradient":
            arr = np.zeros((size, size, 3), dtype=np.uint8)
            for i in range(size):
                arr[i, :, 2] = int(i * 255 / size)
                arr[:, i, 1] = int(i * 200 / size)
        else:
            arr = np.zeros((size, size, 3), dtype=np.uint8)

        img = Image.fromarray(arr, "RGB")
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()
    except ImportError:
        # Fallback: minimal valid JPEG (1x1 white pixel)
        return bytes([
            0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
            0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
            0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
            0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
            0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
            0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
            0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
            0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
            0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x10, 0x01, 0x00, 0x00,
            0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
            0x00, 0x00, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
            0x7F, 0xFF, 0xD9,
        ])


# ---------------------------------------------------------------------------
# Core test runner
# ---------------------------------------------------------------------------

class PipelineTestRunner:
    def __init__(
        self,
        client: APIClient,
        manifest: dict,
        downloaded: dict,
        *,
        top_n: int = 10,
        verbose: bool = False,
        filter_cases: list[str] | None = None,
    ) -> None:
        self.client = client
        self.manifest = manifest
        self.downloaded = downloaded
        self.top_n = top_n
        self.verbose = verbose
        self.filter_cases = filter_cases
        self.results: list[dict] = []

    def _classify_image(self, image_bytes: bytes, filename: str = "test.jpg") -> dict:
        return self.client.post_multipart(
            f"/api/classifier/classify?top_n={self.top_n}",
            filename, image_bytes,
        )

    def _run_labeled_case(self, case: dict) -> list[dict]:
        case_id = case["id"]
        images = self.downloaded.get("cases", {}).get(case_id, [])
        if not images:
            return []

        case_results = []
        acceptable = case["acceptable_labels"]
        min_top_n = case.get("min_top_n", 5)

        for img_record in images:
            img_path = Path(img_record.get("path", ""))
            if not img_path.exists():
                continue

            image_bytes = img_path.read_bytes()
            t0 = time.perf_counter()
            try:
                response = self._classify_image(image_bytes, img_path.name)
                round_trip_ms = round((time.perf_counter() - t0) * 1000, 1)
            except Exception as e:
                print(f"    {_red('ERROR')} {img_path.name}: {e}")
                case_results.append({
                    "case_id": case_id,
                    "image": img_path.name,
                    "status": "error",
                    "error": str(e),
                })
                continue

            predictions = response.get("predictions", [])
            top_score = float(predictions[0]["score"]) if predictions else 0.0
            top_label = predictions[0]["label"] if predictions else ""
            inference_ms = response.get("inference_ms", round_trip_ms)
            model_id = response.get("model_id", "?")
            provider = response.get("active_provider", "?")
            match_rank = _find_match_rank(predictions[:min_top_n], acceptable)
            passed = match_rank is not None

            result = {
                "case_id": case_id,
                "image": img_path.name,
                "status": "pass" if passed else "fail",
                "match_rank": match_rank,
                "top_label": top_label,
                "top_score": top_score,
                "inference_ms": inference_ms,
                "round_trip_ms": round_trip_ms,
                "model_id": model_id,
                "provider": provider,
                "predictions": predictions[:5],
            }
            case_results.append(result)

            if self.verbose or not passed:
                status_str = _green("PASS") if passed else _red("FAIL")
                rank_str = f"@{match_rank}" if match_rank else "not found"
                print(
                    f"    {status_str}  {img_path.name:<40}  "
                    f"{top_label:<35} {top_score:.3f}  "
                    f"{inference_ms:6.0f}ms  [{rank_str}]"
                )
                if not passed and predictions:
                    top5 = ", ".join(f"{p['label']} ({p['score']:.3f})" for p in predictions[:5])
                    print(f"           Top-5: {top5}")

        return case_results

    def _run_rejection_case(self, case: dict) -> dict:
        kind_map = {
            "synthetic_white": "white",
            "synthetic_noise": "noise",
            "synthetic_gradient": "gradient",
        }
        kind = kind_map.get(case["id"], "white")
        max_conf = case.get("max_confidence", 0.9)
        image_bytes = _make_synthetic_image(kind)

        t0 = time.perf_counter()
        try:
            response = self._classify_image(image_bytes, f"{kind}.jpg")
            round_trip_ms = round((time.perf_counter() - t0) * 1000, 1)
        except Exception as e:
            print(f"    {_red('ERROR')} {case['id']}: {e}")
            return {"case_id": case["id"], "status": "error", "error": str(e)}

        predictions = response.get("predictions", [])
        top_score = float(predictions[0]["score"]) if predictions else 0.0
        top_label = predictions[0]["label"] if predictions else ""
        inference_ms = response.get("inference_ms", round_trip_ms)
        passed = top_score < max_conf

        result = {
            "case_id": case["id"],
            "image": kind,
            "status": "pass" if passed else "fail",
            "top_label": top_label,
            "top_score": top_score,
            "max_confidence": max_conf,
            "inference_ms": inference_ms,
            "round_trip_ms": round_trip_ms,
        }

        if self.verbose or not passed:
            status_str = _green("PASS") if passed else _yellow("WARN")
            print(
                f"    {status_str}  {case['id']:<40}  "
                f"{top_label:<35} {top_score:.3f}  {inference_ms:6.0f}ms"
            )

        return result

    def run(self) -> dict[str, Any]:
        manifest = self.manifest
        all_results: list[dict] = []

        # --- Backend diagnostics ---
        print(f"\n{_bold('=== YA-WAMF Pipeline Test ===')}")
        print(f"  Endpoint: {_cyan(self.client.base_url)}")
        try:
            status = self.client.get("/api/classifier/status")
            model_id = status.get("active_model_id", "?")
            provider = status.get("active_provider", "?")
            backend = status.get("inference_backend", "?")
            labels_count = status.get("labels_count", "?")
            loaded = status.get("loaded", False)
            print(f"  Model:    {_cyan(model_id)}  ({labels_count} labels)")
            print(f"  Backend:  {backend}  Provider: {_cyan(provider)}")
            print(f"  Loaded:   {'yes' if loaded else _red('NO — model not loaded!')}")
            if not loaded:
                print(f"\n  {_red('ABORT: model not loaded. Check backend logs.')}")
                return {"status": "abort", "reason": "model not loaded"}

            # GPU / CUDA info
            cuda = status.get("cuda_available", False)
            intel_gpu = status.get("intel_gpu_available", False)
            openvino = status.get("openvino_available", False)
            hw_str = []
            if cuda: hw_str.append("CUDA")
            if intel_gpu: hw_str.append("Intel GPU")
            if openvino: hw_str.append("OpenVINO")
            print(f"  Hardware: {', '.join(hw_str) if hw_str else 'CPU only'}")
        except Exception as e:
            print(f"  {_red(f'Failed to reach API: {e}')}")
            return {"status": "error", "error": str(e)}

        # --- Labeled cases ---
        test_cases = manifest.get("test_cases", [])
        if self.filter_cases:
            test_cases = [c for c in test_cases if c["id"] in self.filter_cases]

        print(f"\n{_bold('--- Labeled Bird Cases ---')}")
        print(f"  {'STATUS':<6}  {'IMAGE':<40}  {'PREDICTED':<35} {'CONF':>5}  {'INF_MS':>7}  RANK")
        print(f"  {'-'*6}  {'-'*40}  {'-'*35} {'-'*5}  {'-'*7}  {'-'*8}")

        labeled_results: list[dict] = []
        for case in test_cases:
            case_id = case["id"]
            images = self.downloaded.get("cases", {}).get(case_id, [])
            if not images:
                print(f"    {_dim(f'SKIP  {case_id} — no images (run download_test_fixtures.py)')} ")
                continue
            print(f"\n  {_bold(case['common_name'])} ({case['scientific_name']})")
            results = self._run_labeled_case(case)
            labeled_results.extend(results)
            all_results.extend(results)

        # --- Rejection cases ---
        print(f"\n{_bold('--- Synthetic Rejection Cases ---')}")
        print(f"  (These should score BELOW threshold — testing the model doesn't hallucinate)")
        rejection_results: list[dict] = []
        for case in manifest.get("rejection_cases", []):
            result = self._run_rejection_case(case)
            rejection_results.append(result)
            all_results.append(result)

        # --- Summary ---
        labeled_pass = sum(1 for r in labeled_results if r.get("status") == "pass")
        labeled_fail = sum(1 for r in labeled_results if r.get("status") == "fail")
        labeled_error = sum(1 for r in labeled_results if r.get("status") == "error")
        labeled_total = labeled_pass + labeled_fail + labeled_error

        rejection_pass = sum(1 for r in rejection_results if r.get("status") == "pass")
        rejection_warn = sum(1 for r in rejection_results if r.get("status") == "fail")

        inf_times = [r["inference_ms"] for r in all_results if "inference_ms" in r and isinstance(r.get("inference_ms"), (int, float))]
        mean_inf = round(sum(inf_times) / len(inf_times), 1) if inf_times else 0
        max_inf = round(max(inf_times), 1) if inf_times else 0

        # Top-1 and top-N accuracy
        top1_matches = [r for r in labeled_results if r.get("match_rank") == 1]
        top3_matches = [r for r in labeled_results if (r.get("match_rank") or 99) <= 3]
        top5_matches = [r for r in labeled_results if (r.get("match_rank") or 99) <= 5]
        evaluated = labeled_pass + labeled_fail

        print(f"\n{_bold('=== Summary ===')}")
        print(f"  Model:           {_cyan(model_id)}")
        print(f"  Provider:        {_cyan(provider)}")
        print()

        if evaluated > 0:
            top1_pct = len(top1_matches) / evaluated * 100
            top3_pct = len(top3_matches) / evaluated * 100
            top5_pct = len(top5_matches) / evaluated * 100
            print(f"  Labeled images:  {labeled_total} evaluated")
            print(f"  Top-1 accuracy:  {_green(f'{top1_pct:.1f}%')}  ({len(top1_matches)}/{evaluated})")
            print(f"  Top-3 accuracy:  {_green(f'{top3_pct:.1f}%')}  ({len(top3_matches)}/{evaluated})")
            print(f"  Top-5 accuracy:  {_green(f'{top5_pct:.1f}%')}  ({len(top5_matches)}/{evaluated})")
            if labeled_fail > 0:
                print(f"  Failed:          {_red(str(labeled_fail))} images not identified in top-5")
            if labeled_error > 0:
                print(f"  Errors:          {_red(str(labeled_error))} images had API errors")
        else:
            print(f"  {_yellow('No labeled images evaluated — run scripts/download_test_fixtures.py first')}")

        print()
        print(f"  Rejection tests: {rejection_pass}/{len(rejection_results)} passed", end="")
        if rejection_warn:
            print(f"  ({_yellow(str(rejection_warn))} high-confidence on synthetic images)")
        else:
            print()

        print()
        print(f"  Mean inference:  {mean_inf:.0f} ms")
        print(f"  Max inference:   {max_inf:.0f} ms")

        # Per-case failures
        failed = [r for r in labeled_results if r.get("status") == "fail"]
        if failed:
            print(f"\n{_bold('--- Failed Cases ---')}")
            for r in failed:
                preds_str = ", ".join(
                    f"{p['label']} ({p['score']:.3f})"
                    for p in r.get("predictions", [])[:3]
                )
                print(f"  {_red('FAIL')}  {r['case_id']}/{r['image']}")
                print(f"        Top-3 predicted: {preds_str}")

        overall_ok = labeled_fail == 0 and labeled_error == 0
        print(f"\n  Overall: {_green('PASS') if overall_ok else _red('FAIL')}")

        return {
            "model_id": model_id,
            "provider": provider,
            "labeled": {
                "total": labeled_total,
                "pass": labeled_pass,
                "fail": labeled_fail,
                "error": labeled_error,
                "top1_accuracy": round(len(top1_matches) / evaluated, 4) if evaluated else None,
                "top3_accuracy": round(len(top3_matches) / evaluated, 4) if evaluated else None,
                "top5_accuracy": round(len(top5_matches) / evaluated, 4) if evaluated else None,
            },
            "rejection": {
                "total": len(rejection_results),
                "pass": rejection_pass,
                "warn": rejection_warn,
            },
            "timing": {
                "mean_inference_ms": mean_inf,
                "max_inference_ms": max_inf,
            },
            "results": all_results,
        }


# ---------------------------------------------------------------------------
# Model cycling
# ---------------------------------------------------------------------------

def _get_installed_models(client: APIClient) -> list[dict]:
    try:
        return client.get("/api/models/installed")
    except Exception as e:
        print(f"  {_red(f'Failed to fetch installed models: {e}')}")
        return []


def _activate_model(client: APIClient, model_id: str) -> bool:
    try:
        result = client.post_json(f"/api/models/{model_id}/activate", {})
        return result.get("status") == "ok"
    except Exception as e:
        print(f"  {_red(f'Failed to activate {model_id}: {e}')}")
        return False


def _wait_for_model_loaded(client: APIClient, expected_id: str, timeout: float = 60.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            status = client.get("/api/classifier/status")
            if status.get("loaded") and status.get("active_model_id") == expected_id:
                return True
        except Exception:
            pass
        time.sleep(2)
    return False


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="YA-WAMF pipeline test runner — exercises the live API with labeled bird images"
    )
    parser.add_argument("--base_url", default="http://localhost:8946", help="Backend base URL (default: http://localhost:8946)")
    parser.add_argument("--api_key", default=None, help="API key (if auth is enabled)")
    parser.add_argument("--top_n", type=int, default=10, help="Top-N predictions to request (default: 10)")
    parser.add_argument("--cases", help="Comma-separated list of case IDs to run (default: all)")
    parser.add_argument("--verbose", action="store_true", help="Print every image result, not just failures")
    parser.add_argument("--output", help="Write JSON report to this file")
    parser.add_argument("--all_models", action="store_true", help="Cycle through all installed models (activates each in turn)")
    parser.add_argument("--manifest", default=str(_MANIFEST_PATH), help="Path to bird_image_manifest.json")
    parser.add_argument("--images_dir", default=str(_IMAGES_DIR), help="Path to downloaded fixture images")
    args = parser.parse_args()

    manifest_path = Path(args.manifest)
    downloaded_path = Path(args.images_dir) / "downloaded.json"

    if not manifest_path.exists():
        print(f"ERROR: manifest not found at {manifest_path}", file=sys.stderr)
        return 1
    if not downloaded_path.exists():
        print(
            f"ERROR: no downloaded images found at {downloaded_path}\n"
            f"Run:  python scripts/download_test_fixtures.py",
            file=sys.stderr,
        )
        return 1

    manifest = json.loads(manifest_path.read_text())
    downloaded = json.loads(downloaded_path.read_text())
    filter_cases = [c.strip() for c in args.cases.split(",")] if args.cases else None

    client = APIClient(args.base_url, api_key=args.api_key)

    if args.all_models:
        installed = _get_installed_models(client)
        if not installed:
            print("No installed models found.", file=sys.stderr)
            return 1

        original_model = None
        try:
            status = client.get("/api/classifier/status")
            original_model = status.get("active_model_id")
        except Exception:
            pass

        all_reports: list[dict] = []
        model_ids = [m["id"] for m in installed if m.get("id")]
        print(f"\nCycling through {len(model_ids)} installed models: {', '.join(model_ids)}")

        for model_id in model_ids:
            print(f"\n{'='*60}")
            print(f"  Activating model: {_cyan(model_id)}")
            if not _activate_model(client, model_id):
                print(f"  {_red('SKIP')}: activation failed")
                continue
            if not _wait_for_model_loaded(client, model_id, timeout=90):
                print(f"  {_red('SKIP')}: model did not load within 90s")
                continue
            time.sleep(1)

            runner = PipelineTestRunner(
                client, manifest, downloaded,
                top_n=args.top_n, verbose=args.verbose, filter_cases=filter_cases,
            )
            report = runner.run()
            report["model_id"] = model_id
            all_reports.append(report)

        # Restore original model
        if original_model:
            print(f"\nRestoring original model: {original_model}")
            _activate_model(client, original_model)

        # Multi-model summary
        print(f"\n{_bold('=== Multi-Model Comparison ===')}")
        print(f"  {'MODEL':<35} {'TOP-1':>6} {'TOP-5':>6} {'MEAN_INF':>9} {'PROVIDER'}")
        print(f"  {'-'*35} {'-'*6} {'-'*6} {'-'*9} {'-'*20}")
        for r in all_reports:
            labeled = r.get("labeled", {})
            t1 = f"{labeled.get('top1_accuracy', 0)*100:.1f}%" if labeled.get("top1_accuracy") is not None else "—"
            t5 = f"{labeled.get('top5_accuracy', 0)*100:.1f}%" if labeled.get("top5_accuracy") is not None else "—"
            inf = f"{r.get('timing', {}).get('mean_inference_ms', 0):.0f}ms"
            prov = r.get("provider", "?")
            print(f"  {r['model_id']:<35} {t1:>6} {t5:>6} {inf:>9} {prov}")

        if args.output:
            Path(args.output).write_text(json.dumps(all_reports, indent=2))
            print(f"\nJSON report written to {args.output}")

        return 0

    # Single model run
    runner = PipelineTestRunner(
        client, manifest, downloaded,
        top_n=args.top_n, verbose=args.verbose, filter_cases=filter_cases,
    )
    report = runner.run()

    if args.output:
        Path(args.output).write_text(json.dumps(report, indent=2))
        print(f"\nJSON report written to {args.output}")

    return 0 if report.get("labeled", {}).get("fail", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
