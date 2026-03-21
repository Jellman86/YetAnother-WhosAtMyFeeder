"""Accuracy evaluation harness for ONNX bird classification models.

Evaluates a model against a labeled image dataset (CUB-200-2011 or custom)
and reports top-1/top-5 accuracy, mean confidence, unknown rate, and
per-threshold precision/recall.

Usage:
    # Download CUB-200-2011 and evaluate
    python scripts/eval_model_accuracy.py \\
        --model_dir data/models/convnext_large_inat21 \\
        --dataset_dir data/eval/CUB_200_2011 \\
        --dataset_format cub200

    # Evaluate against a flat directory of labelled images
    # (each subdirectory name is the ground-truth label)
    python scripts/eval_model_accuracy.py \\
        --model_dir data/models/eu_medium_focalnet_b \\
        --dataset_dir data/eval/my_birds \\
        --dataset_format directory

    # Download CUB-200-2011 then evaluate
    python scripts/eval_model_accuracy.py \\
        --model_dir data/models/convnext_large_inat21 \\
        --dataset_dir data/eval \\
        --download_cub

Dataset formats:
    cub200     - CUB-200-2011 (uses test split by default)
    directory  - Flat labelled dirs: dataset_dir/<label>/<image>.jpg
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
import tarfile
import shutil
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

try:
    import onnxruntime as ort
    ORT_AVAILABLE = True
except ImportError:
    ORT_AVAILABLE = False


# ---------------------------------------------------------------------------
# Preprocessing helpers
# ---------------------------------------------------------------------------

def _resize_center_crop(img: Image.Image, size: int, crop_pct: float) -> Image.Image:
    scale_size = int(size / crop_pct)
    w, h = img.size
    if w < h:
        new_w = scale_size
        new_h = int(h * scale_size / w)
    else:
        new_h = scale_size
        new_w = int(w * scale_size / h)
    img = img.resize((new_w, new_h), Image.BICUBIC)
    left = (new_w - size) // 2
    top = (new_h - size) // 2
    return img.crop((left, top, left + size, top + size))


def _resize_direct(img: Image.Image, size: int) -> Image.Image:
    return img.resize((size, size), Image.BICUBIC)


def preprocess_image(img_path: Path, config: dict) -> np.ndarray:
    """Preprocess a single image according to model_config.json parameters."""
    pre = config.get("preprocessing", {})
    input_size = config.get("input_size", 224)
    mean = np.array(pre.get("mean", [0.485, 0.456, 0.406]), dtype=np.float32)
    std = np.array(pre.get("std", [0.229, 0.224, 0.225]), dtype=np.float32)
    crop_pct = float(pre.get("crop_pct", 1.0))
    resize_mode = pre.get("resize_mode", "center_crop")
    color_space = pre.get("color_space", "RGB").upper()

    img = Image.open(img_path).convert("RGB")

    if resize_mode == "center_crop":
        img = _resize_center_crop(img, input_size, crop_pct if crop_pct > 0 else 1.0)
    else:
        img = _resize_direct(img, input_size)

    if color_space == "BGR":
        img = img.convert("RGB")
        arr = np.array(img, dtype=np.float32)[:, :, ::-1]
    else:
        arr = np.array(img, dtype=np.float32)

    arr /= 255.0
    arr = (arr - mean) / std
    arr = arr.transpose(2, 0, 1)  # HWC → CHW
    return arr[np.newaxis].astype(np.float32)


# ---------------------------------------------------------------------------
# Label matching helpers
# ---------------------------------------------------------------------------

def _normalise_label(label: str) -> str:
    """Lowercase, replace underscores/dashes with spaces, strip."""
    return label.lower().replace("_", " ").replace("-", " ").strip()


def build_label_index(labels: list[str]) -> dict[str, int]:
    return {_normalise_label(lbl): i for i, lbl in enumerate(labels)}


def match_ground_truth(gt: str, label_index: dict[str, int]) -> int | None:
    """Return model label index matching ground-truth string, or None."""
    key = _normalise_label(gt)
    if key in label_index:
        return label_index[key]
    # Partial match: ground-truth is a substring of a model label
    for lbl_norm, idx in label_index.items():
        if key in lbl_norm or lbl_norm in key:
            return idx
    return None


# ---------------------------------------------------------------------------
# Dataset loaders
# ---------------------------------------------------------------------------

def _load_cub200(dataset_dir: Path, split: str = "test") -> list[tuple[Path, str]]:
    """Load CUB-200-2011 image paths with class names.

    Returns list of (image_path, class_name) pairs.
    """
    base = dataset_dir / "CUB_200_2011"
    if not base.exists():
        raise FileNotFoundError(
            f"CUB-200-2011 not found at {base}. Use --download_cub to download."
        )

    # Load class names: <class_id> <name>  e.g. 001.Black_footed_Albatross
    class_names: dict[str, str] = {}
    with open(base / "classes.txt") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                cid, name = parts[0], parts[1]
                # Strip leading "001." prefix
                class_names[cid] = name.split(".", 1)[-1].replace("_", " ")

    # Load image list: <image_id> <path>
    image_paths: dict[str, Path] = {}
    with open(base / "images.txt") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                image_paths[parts[0]] = base / "images" / parts[1]

    # Load image → class mapping
    image_classes: dict[str, str] = {}
    with open(base / "image_class_labels.txt") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2:
                image_classes[parts[0]] = class_names.get(parts[1], parts[1])

    # Load train/test split: 0=train, 1=test
    split_flag = "1" if split == "test" else "0"
    selected_ids: set[str] = set()
    with open(base / "train_test_split.txt") as f:
        for line in f:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[1] == split_flag:
                selected_ids.add(parts[0])

    samples = []
    for img_id in sorted(selected_ids):
        if img_id in image_paths and img_id in image_classes:
            samples.append((image_paths[img_id], image_classes[img_id]))

    return samples


def _load_directory(dataset_dir: Path) -> list[tuple[Path, str]]:
    """Load labelled directory: dataset_dir/<label>/<image>.*"""
    samples = []
    img_exts = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
    for label_dir in sorted(dataset_dir.iterdir()):
        if not label_dir.is_dir():
            continue
        label = label_dir.name
        for img_file in sorted(label_dir.iterdir()):
            if img_file.suffix.lower() in img_exts:
                samples.append((img_file, label))
    return samples


# ---------------------------------------------------------------------------
# CUB-200-2011 downloader
# ---------------------------------------------------------------------------

def download_cub200(dest_dir: Path) -> None:
    """Download and extract CUB-200-2011 into dest_dir."""
    url = "https://data.caltech.edu/records/65de6-vp158/files/CUB_200_2011.tgz"
    dest_dir.mkdir(parents=True, exist_ok=True)
    tgz_path = dest_dir / "CUB_200_2011.tgz"

    if (dest_dir / "CUB_200_2011").exists():
        print(f"CUB-200-2011 already exists at {dest_dir / 'CUB_200_2011'}, skipping download.")
        return

    print(f"Downloading CUB-200-2011 (~1.1 GB) to {tgz_path} ...")

    def _reporthook(block_num: int, block_size: int, total_size: int) -> None:
        downloaded = block_num * block_size
        if total_size > 0:
            pct = min(100, downloaded * 100 // total_size)
            mb = downloaded / 1024 / 1024
            total_mb = total_size / 1024 / 1024
            print(f"\r  {pct}% ({mb:.0f}/{total_mb:.0f} MB)", end="", flush=True)

    urllib.request.urlretrieve(url, tgz_path, _reporthook)
    print()

    print("Extracting ...")
    with tarfile.open(tgz_path, "r:gz") as tar:
        tar.extractall(dest_dir)
    tgz_path.unlink()
    print(f"Done. Dataset at {dest_dir / 'CUB_200_2011'}")


# ---------------------------------------------------------------------------
# Evaluation core
# ---------------------------------------------------------------------------

class ModelEvaluator:
    def __init__(self, model_dir: Path) -> None:
        self.model_dir = model_dir
        config_path = model_dir / "model_config.json"
        labels_path = model_dir / "labels.txt"
        model_path = model_dir / "model.onnx"

        if not config_path.exists():
            raise FileNotFoundError(f"model_config.json not found in {model_dir}")
        if not labels_path.exists():
            raise FileNotFoundError(f"labels.txt not found in {model_dir}")
        if not model_path.exists():
            raise FileNotFoundError(f"model.onnx not found in {model_dir}")

        self.config: dict[str, Any] = json.loads(config_path.read_text())
        self.labels: list[str] = [
            l.strip() for l in labels_path.read_text().splitlines() if l.strip()
        ]
        self.label_index = build_label_index(self.labels)

        providers = ["CPUExecutionProvider"]
        so = ort.SessionOptions()
        so.intra_op_num_threads = 4
        so.inter_op_num_threads = 2
        self.session = ort.InferenceSession(str(model_path), so, providers=providers)
        self.input_name = self.session.get_inputs()[0].name

        print(f"Loaded model: {model_dir.name}")
        print(f"  Labels: {len(self.labels)}, Input: {self.config.get('input_size')}px")
        print(f"  Taxonomy scope: {self.config.get('taxonomy_scope', 'unknown')}")

    def predict(self, img_path: Path) -> tuple[list[str], list[float]]:
        """Return top-5 (label, score) pairs."""
        tensor = preprocess_image(img_path, self.config)
        outputs = self.session.run(None, {self.input_name: tensor})[0][0]
        # Softmax
        exp = np.exp(outputs - outputs.max())
        probs = exp / exp.sum()
        top5_idx = np.argsort(probs)[::-1][:5]
        return (
            [self.labels[i] for i in top5_idx],
            [float(probs[i]) for i in top5_idx],
        )

    def evaluate(
        self,
        samples: list[tuple[Path, str]],
        threshold: float = 0.0,
        max_samples: int | None = None,
        verbose: bool = False,
    ) -> dict[str, Any]:
        if max_samples:
            samples = samples[:max_samples]

        top1_correct = 0
        top5_correct = 0
        unknown_count = 0
        total = 0
        matched_total = 0
        sum_top1_score = 0.0
        sum_top1_score_correct = 0.0
        unmatched_gts: dict[str, int] = defaultdict(int)
        per_class_results: dict[str, dict[str, int]] = defaultdict(lambda: {"correct": 0, "total": 0})
        inference_times: list[float] = []

        for img_path, gt_label in samples:
            if not img_path.exists():
                continue

            try:
                t0 = time.perf_counter()
                top_labels, top_scores = self.predict(img_path)
                inference_times.append(time.perf_counter() - t0)
            except Exception as e:
                if verbose:
                    print(f"  ERROR {img_path}: {e}")
                continue

            total += 1
            gt_idx = match_ground_truth(gt_label, self.label_index)

            if gt_idx is None:
                unmatched_gts[gt_label] += 1
                continue
            matched_total += 1

            matched_gt = self.labels[gt_idx]
            per_class_results[matched_gt]["total"] += 1

            top1_score = top_scores[0]
            sum_top1_score += top1_score

            if top1_score < threshold:
                unknown_count += 1
                if verbose:
                    print(f"  UNKNOWN {img_path.name}: {top_labels[0]} ({top1_score:.3f}) | GT: {gt_label}")
                continue

            pred_label = top_labels[0]
            pred_in_top5 = top_labels

            top1_hit = _normalise_label(pred_label) == _normalise_label(matched_gt)
            top5_hit = any(_normalise_label(l) == _normalise_label(matched_gt) for l in pred_in_top5)

            if top1_hit:
                top1_correct += 1
                sum_top1_score_correct += top1_score
                per_class_results[matched_gt]["correct"] += 1
            if top5_hit:
                top5_correct += 1

            if verbose and not top1_hit:
                print(
                    f"  WRONG {img_path.name}: pred={pred_label} ({top1_score:.3f}) | GT: {gt_label}"
                )

        evaluated = matched_total - unknown_count
        top1_acc = top1_correct / evaluated if evaluated > 0 else 0.0
        top5_acc = top5_correct / evaluated if evaluated > 0 else 0.0
        unknown_rate = unknown_count / matched_total if matched_total > 0 else 0.0
        mean_conf = sum_top1_score / matched_total if matched_total > 0 else 0.0
        mean_conf_correct = sum_top1_score_correct / top1_correct if top1_correct > 0 else 0.0
        median_inf = float(np.median(inference_times)) if inference_times else 0.0
        p95_inf = float(np.percentile(inference_times, 95)) if inference_times else 0.0

        # Per-class accuracy (worst 10)
        class_accs = []
        for cls, counts in per_class_results.items():
            if counts["total"] > 0:
                class_accs.append((cls, counts["correct"] / counts["total"], counts["total"]))
        class_accs.sort(key=lambda x: x[1])

        return {
            "total_images": total,
            "matched_to_model": matched_total,
            "evaluated_above_threshold": evaluated,
            "unknown_count": unknown_count,
            "top1_correct": top1_correct,
            "top5_correct": top5_correct,
            "top1_accuracy": round(top1_acc, 4),
            "top5_accuracy": round(top5_acc, 4),
            "unknown_rate": round(unknown_rate, 4),
            "mean_confidence": round(mean_conf, 4),
            "mean_confidence_correct_only": round(mean_conf_correct, 4),
            "median_inference_ms": round(median_inf * 1000, 2),
            "p95_inference_ms": round(p95_inf * 1000, 2),
            "threshold_used": threshold,
            "unmatched_ground_truth_labels": dict(sorted(
                unmatched_gts.items(), key=lambda x: -x[1]
            )[:20]),
            "worst_10_classes": [
                {"class": c, "accuracy": round(a, 3), "count": n}
                for c, a, n in class_accs[:10]
            ],
            "best_10_classes": [
                {"class": c, "accuracy": round(a, 3), "count": n}
                for c, a, n in class_accs[-10:][::-1]
            ],
        }


def sweep_thresholds(
    evaluator: ModelEvaluator,
    samples: list[tuple[Path, str]],
    thresholds: list[float],
    max_samples: int | None = None,
) -> list[dict[str, Any]]:
    """Run evaluation at multiple thresholds and return results list."""
    results = []
    for thresh in thresholds:
        print(f"  threshold={thresh:.2f} ...", end=" ", flush=True)
        r = evaluator.evaluate(samples, threshold=thresh, max_samples=max_samples)
        print(
            f"top1={r['top1_accuracy']:.1%}  top5={r['top5_accuracy']:.1%}"
            f"  unknown={r['unknown_rate']:.1%}  mean_conf={r['mean_confidence']:.3f}"
        )
        results.append(r)
    return results


def print_report(results: dict[str, Any], model_dir: str) -> None:
    print()
    print("=" * 62)
    print(f"  Model: {model_dir}")
    print(f"  Threshold: {results['threshold_used']}")
    print("=" * 62)
    print(f"  Images evaluated:  {results['evaluated_above_threshold']}/{results['matched_to_model']} matched")
    print(f"  Top-1 accuracy:    {results['top1_accuracy']:.1%}  ({results['top1_correct']} correct)")
    print(f"  Top-5 accuracy:    {results['top5_accuracy']:.1%}  ({results['top5_correct']} correct)")
    print(f"  Unknown rate:      {results['unknown_rate']:.1%}  ({results['unknown_count']} below threshold)")
    print(f"  Mean confidence:   {results['mean_confidence']:.3f}")
    print(f"  Mean conf (correct): {results['mean_confidence_correct_only']:.3f}")
    print(f"  Median inference:  {results['median_inference_ms']:.1f} ms")
    print(f"  P95 inference:     {results['p95_inference_ms']:.1f} ms")
    if results["unmatched_ground_truth_labels"]:
        print(f"\n  Unmatched GT labels ({len(results['unmatched_ground_truth_labels'])}):")
        for lbl, count in list(results["unmatched_ground_truth_labels"].items())[:5]:
            print(f"    {lbl!r}: {count} images")
    if results["worst_10_classes"]:
        print("\n  Worst classes:")
        for entry in results["worst_10_classes"][:5]:
            print(f"    {entry['class']}: {entry['accuracy']:.1%} ({entry['count']} images)")
    print("=" * 62)


def save_csv(sweep_results: list[dict[str, Any]], out_path: Path) -> None:
    if not sweep_results:
        return
    fieldnames = [
        "threshold_used", "top1_accuracy", "top5_accuracy", "unknown_rate",
        "mean_confidence", "median_inference_ms", "p95_inference_ms",
        "top1_correct", "top5_correct", "evaluated_above_threshold",
        "unknown_count", "matched_to_model",
    ]
    with open(out_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(sweep_results)
    print(f"\nCSV saved to {out_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate ONNX bird model accuracy against a labelled dataset"
    )
    parser.add_argument("--model_dir", required=True, help="Path to model directory (must contain model.onnx, labels.txt, model_config.json)")
    parser.add_argument("--dataset_dir", required=True, help="Dataset directory")
    parser.add_argument(
        "--dataset_format",
        default="directory",
        choices=["cub200", "directory"],
        help="Dataset format: cub200 or directory (default: directory)",
    )
    parser.add_argument("--split", default="test", choices=["train", "test"], help="CUB-200-2011 split to use (default: test)")
    parser.add_argument("--download_cub", action="store_true", help="Download CUB-200-2011 into dataset_dir")
    parser.add_argument("--threshold", type=float, default=None, help="Confidence threshold (default: use model recommended_threshold or 0.0)")
    parser.add_argument("--sweep", action="store_true", help="Sweep multiple thresholds (0.0, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)")
    parser.add_argument("--max_samples", type=int, default=None, help="Limit number of images evaluated")
    parser.add_argument("--verbose", action="store_true", help="Print per-image wrong predictions")
    parser.add_argument("--output_json", type=str, default=None, help="Write full results to JSON")
    parser.add_argument("--output_csv", type=str, default=None, help="Write threshold sweep to CSV")
    args = parser.parse_args()

    if not ORT_AVAILABLE:
        print("ERROR: onnxruntime is required. pip install onnxruntime", file=sys.stderr)
        return 1

    model_dir = Path(args.model_dir)
    dataset_dir = Path(args.dataset_dir)

    if args.download_cub:
        download_cub200(dataset_dir)

    print(f"\nLoading model from {model_dir} ...")
    evaluator = ModelEvaluator(model_dir)

    # Read recommended threshold from model_config if not specified
    threshold = args.threshold
    if threshold is None:
        threshold = evaluator.config.get("recommended_threshold", 0.0)
        if threshold:
            print(f"Using recommended threshold from model_config: {threshold}")

    print(f"\nLoading dataset ({args.dataset_format}) from {dataset_dir} ...")
    if args.dataset_format == "cub200":
        samples = _load_cub200(dataset_dir, split=args.split)
    else:
        samples = _load_directory(dataset_dir)

    print(f"  {len(samples)} samples loaded")

    if not samples:
        print("ERROR: No samples found.", file=sys.stderr)
        return 1

    if args.sweep:
        thresholds = [0.0, 0.3, 0.35, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.75, 0.8]
        print(f"\nSweeping {len(thresholds)} thresholds ...")
        sweep_results = sweep_thresholds(evaluator, samples, thresholds, max_samples=args.max_samples)
        if args.output_csv:
            save_csv(sweep_results, Path(args.output_csv))
        # Print the recommended threshold result
        closest = min(sweep_results, key=lambda r: abs(r["threshold_used"] - (threshold or 0.0)))
        print_report(closest, str(model_dir))
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(sweep_results, indent=2))
            print(f"JSON saved to {args.output_json}")
    else:
        print(f"\nEvaluating at threshold={threshold} ...")
        results = evaluator.evaluate(
            samples,
            threshold=threshold or 0.0,
            max_samples=args.max_samples,
            verbose=args.verbose,
        )
        print_report(results, str(model_dir))
        if args.output_json:
            Path(args.output_json).write_text(json.dumps(results, indent=2))
            print(f"JSON saved to {args.output_json}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
