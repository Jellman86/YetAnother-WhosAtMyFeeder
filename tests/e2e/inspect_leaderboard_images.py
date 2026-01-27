#!/usr/bin/env python3
"""Inspect leaderboard images and capture failures."""
import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _failure_text(failure):
    if not failure:
        return None
    if isinstance(failure, dict):
        return failure.get("errorText")
    return str(failure)


def run(url: str, output: str, wait_seconds: float) -> None:
    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    results = {
        "url": url,
        "captured_at": utc_now_iso(),
        "console": [],
        "pageerrors": [],
        "requestfailed": [],
        "response_errors": [],
        "image_summary": {},
        "images": [],
    }

    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        def on_console(msg):
            results["console"].append(
                {
                    "timestamp": utc_now_iso(),
                    "type": msg.type,
                    "text": msg.text,
                    "location": getattr(msg, "location", None),
                }
            )

        def on_pageerror(err):
            results["pageerrors"].append(
                {"timestamp": utc_now_iso(), "message": str(err)}
            )

        def on_request_failed(request):
            failure = request.failure
            results["requestfailed"].append(
                {
                    "timestamp": utc_now_iso(),
                    "url": request.url,
                    "method": request.method,
                    "resource_type": request.resource_type,
                    "failure": _failure_text(failure),
                }
            )

        def on_response(response):
            if response.status >= 400:
                results["response_errors"].append(
                    {
                        "timestamp": utc_now_iso(),
                        "url": response.url,
                        "status": response.status,
                        "status_text": response.status_text,
                        "resource_type": response.request.resource_type,
                    }
                )

        page.on("console", on_console)
        page.on("pageerror", on_pageerror)
        page.on("requestfailed", on_request_failed)
        page.on("response", on_response)

        page.goto(url)
        page.wait_for_load_state("domcontentloaded")
        time.sleep(wait_seconds)

        images = page.evaluate(
            """
            () => {
              const imgs = Array.from(document.querySelectorAll('img'));
              return imgs.map((img, idx) => ({
                index: idx,
                alt: img.getAttribute('alt'),
                src: img.currentSrc || img.src || null,
                width: img.naturalWidth,
                height: img.naturalHeight,
                complete: img.complete,
                visible: !!(img.offsetWidth || img.offsetHeight || img.getClientRects().length)
              }));
            }
            """
        )

        results["images"] = images
        results["image_summary"] = {
            "total": len(images),
            "loaded": sum(1 for i in images if i.get("complete") and i.get("width", 0) > 0),
            "broken": sum(1 for i in images if i.get("complete") and i.get("width", 0) == 0),
        }

        page.screenshot(path=str(out_path.with_suffix('.png')), full_page=True)
        browser.close()

    with out_path.open("w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)

    print(f"Wrote report: {out_path}")
    print(f"Screenshot: {out_path.with_suffix('.png')}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--url",
        default="http://yawamf-frontend/leaderboard",
        help="Leaderboard URL to inspect",
    )
    parser.add_argument(
        "--output",
        default="/config/workspace/playwright-results/leaderboard/leaderboard-image-inspect.json",
        help="Output JSON report path",
    )
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=8.0,
        help="Wait after DOMContentLoaded before inspection",
    )
    args = parser.parse_args()

    run(args.url, args.output, args.wait_seconds)
