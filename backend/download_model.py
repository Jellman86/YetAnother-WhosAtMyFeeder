#!/usr/bin/env python3
"""
Download bird classification model and labels for YA-WAMF.

This script downloads the Google AIY Vision Bird Classifier model (MobileNetV2)
which can identify 964 bird species.

Usage:
    python download_model.py

The model and labels will be saved to backend/app/assets/
"""

import os
import sys
import urllib.request
from pathlib import Path

# URLs for the Google AIY Bird Classifier
MODEL_URL = "https://storage.googleapis.com/tfhub-lite-models/google/lite-model/aiy/vision/classifier/birds_V1/3.tflite"
LABELS_URL = "https://raw.githubusercontent.com/google-coral/edgetpu/master/test_data/inat_bird_labels.txt"

# Determine assets directory (works from project root or backend directory)
SCRIPT_DIR = Path(__file__).parent
ASSETS_DIR = SCRIPT_DIR / "app" / "assets"

# Ensure assets directory exists
ASSETS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_PATH = ASSETS_DIR / "model.tflite"
LABELS_PATH = ASSETS_DIR / "labels.txt"


def download_file(url: str, dest: Path, desc: str) -> bool:
    """Download a file with progress indication."""
    print(f"Downloading {desc}...")
    print(f"  From: {url}")
    print(f"  To: {dest}")

    try:
        def progress_hook(block_num, block_size, total_size):
            if total_size > 0:
                percent = min(100, block_num * block_size * 100 // total_size)
                mb_downloaded = block_num * block_size / (1024 * 1024)
                mb_total = total_size / (1024 * 1024)
                print(f"\r  Progress: {percent}% ({mb_downloaded:.1f}/{mb_total:.1f} MB)", end="", flush=True)

        urllib.request.urlretrieve(url, dest, progress_hook)
        print()  # New line after progress
        return True
    except Exception as e:
        print(f"\n  Error: {e}")
        return False


def process_labels(labels_path: Path) -> bool:
    """Process the labels file to extract just the common names."""
    print("Processing labels file...")
    try:
        with open(labels_path, 'r') as f:
            lines = f.readlines()

        processed_labels = []
        for line in lines:
            line = line.strip()
            if not line:
                continue

            # Format is: "index Scientific name (Common Name)" or just "background"
            if '(' in line and ')' in line:
                # Extract common name from parentheses
                start = line.rfind('(') + 1
                end = line.rfind(')')
                common_name = line[start:end].strip()
                processed_labels.append(common_name)
            else:
                # Handle entries without parentheses (like "background")
                parts = line.split(' ', 1)
                if len(parts) > 1:
                    processed_labels.append(parts[1])
                else:
                    processed_labels.append(line)

        # Write processed labels
        with open(labels_path, 'w') as f:
            for label in processed_labels:
                f.write(f"{label}\n")

        print(f"  Processed {len(processed_labels)} labels")
        return True
    except Exception as e:
        print(f"  Error processing labels: {e}")
        return False


def main():
    print("=" * 60)
    print("YA-WAMF Bird Classification Model Downloader")
    print("=" * 60)
    print()
    print("This will download the Google AIY Vision Bird Classifier")
    print("(MobileNetV2, trained on iNaturalist, 964 species)")
    print()

    # Check if model already exists
    if MODEL_PATH.exists():
        response = input(f"Model already exists at {MODEL_PATH}. Overwrite? [y/N]: ")
        if response.lower() != 'y':
            print("Skipping model download.")
        else:
            if not download_file(MODEL_URL, MODEL_PATH, "bird classifier model"):
                sys.exit(1)
    else:
        if not download_file(MODEL_URL, MODEL_PATH, "bird classifier model"):
            sys.exit(1)

    # Download labels
    if not download_file(LABELS_URL, LABELS_PATH, "species labels"):
        sys.exit(1)

    # Process labels to extract common names
    if not process_labels(LABELS_PATH):
        sys.exit(1)

    print()
    print("=" * 60)
    print("Download complete!")
    print("=" * 60)
    print()
    print(f"Model: {MODEL_PATH}")
    print(f"Labels: {LABELS_PATH}")
    print()
    print("You can now restart the backend to use the classifier.")
    print()
    print("Note: You can replace these files with your own model and labels")
    print("if you want to use a different bird classifier.")


if __name__ == "__main__":
    main()
