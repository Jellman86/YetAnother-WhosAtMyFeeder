#!/usr/bin/env python3
"""
Capture browser console messages and page errors for a given URL.
"""
import argparse
import json
import os
import time
from datetime import datetime, timezone

from playwright.sync_api import sync_playwright


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run(url: str, output: str, wait_seconds: float) -> None:
    os.makedirs(os.path.dirname(output), exist_ok=True)

    results = {
        "url": url,
        "captured_at": utc_now_iso(),
        "console": [],
        "pageerrors": [],
        "console_errors": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        def on_console(msg):
            entry = {
                "timestamp": utc_now_iso(),
                "type": msg.type,
                "text": msg.text,
            }
            try:
                entry["location"] = msg.location
            except Exception:
                pass
            results["console"].append(entry)

        def on_pageerror(err):
            results["pageerrors"].append(
                {"timestamp": utc_now_iso(), "message": str(err)}
            )

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)

        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(wait_seconds)

        browser.close()

    results["console_errors"] = [
        entry
        for entry in results["console"]
        if entry.get("type") in {"error", "warning"}
    ]

    with open(output, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote console log capture: {output}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="https://yetanotherwhosatmyfeeder.pownet.uk/",
        help="Target URL to capture console logs from",
    )
    parser.add_argument(
        "--output",
        default="/config/workspace/playwright-results/lighthouse-public/console-errors.json",
        help="Output JSON file path",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=8.0,
        help="How long to wait after DOMContentLoaded to capture logs",
    )
    args = parser.parse_args()

    run(args.url, args.output, args.wait_seconds)


if __name__ == "__main__":
    main()
