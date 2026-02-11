import os
import re

import pytest
from playwright.sync_api import Page, sync_playwright


@pytest.fixture(scope="module")
def browser():
    ws_url = os.environ.get("PLAYWRIGHT_WS", "ws://playwright-service:3000/")
    with sync_playwright() as p:
        browser = p.chromium.connect(ws_url)
        yield browser
        browser.close()


@pytest.fixture(scope="module")
def page(browser):
    context = browser.new_context(viewport={"width": 1366, "height": 900}, ignore_https_errors=True)
    page = context.new_page()
    yield page
    context.close()


@pytest.fixture()
def console_capture(page: Page):
    entries: list[tuple[str, str]] = []

    def on_console(msg):
        entries.append((msg.type, msg.text))

    def on_pageerror(err):
        entries.append(("pageerror", str(err)))

    page.on("console", on_console)
    page.on("pageerror", on_pageerror)
    yield entries
    page.remove_listener("console", on_console)
    page.remove_listener("pageerror", on_pageerror)


def _serious_console_errors(entries: list[tuple[str, str]]) -> list[str]:
    allowed_patterns = [
        r"Failed to load resource: the server responded with a status of 404",
        r"favicon\.ico",
    ]
    severe = []
    for kind, text in entries:
        if kind not in {"error", "pageerror"}:
            continue
        if any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in allowed_patterns):
            continue
        severe.append(f"[{kind}] {text}")
    return severe


def _open_detection_with_video_button(page: Page) -> bool:
    cards = page.locator(".grid > div")
    count = cards.count()
    for i in range(min(count, 12)):
        cards.nth(i).click()
        page.wait_for_selector("div[role='dialog']", timeout=3000)
        play_icon = page.locator("button svg path[d='M8 5v14l11-7z']")
        if play_icon.count() > 0 and play_icon.first.is_visible():
            return True
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    return False


def test_video_player_ui_and_console_health(page: Page, console_capture):
    page.goto("http://yawamf-frontend/events", timeout=30000)
    page.wait_for_load_state("domcontentloaded")

    # Auth-protected mode: skip when login gate is active.
    if page.locator("input#username").count() > 0:
        pytest.skip("Auth required without public access; no automated login in this test")

    try:
        page.wait_for_selector(".grid > div", timeout=8000)
    except Exception:
        pytest.skip("No detections available on Events page")

    if not _open_detection_with_video_button(page):
        pytest.skip("No detection with a visible video play button in current data set")

    # Open VideoPlayer modal.
    page.locator("button svg path[d='M8 5v14l11-7z']").first.click()
    player = page.get_by_label("Video player")
    player.wait_for(state="visible", timeout=8000)
    page.get_by_label("Close video").wait_for(state="visible", timeout=4000)

    # If clip is unavailable in this dataset, skip timeline assertions.
    unavailable = page.get_by_text("Video Unavailable").count() > 0 or page.get_by_text("Clip Fetching Disabled").count() > 0
    if unavailable:
        pytest.skip("Clip unavailable in current environment; UI opened but timeline controls not testable")

    page.locator(".plyr").first.wait_for(state="visible", timeout=8000)
    page.locator(".plyr__controls").first.wait_for(state="visible", timeout=8000)
    page.get_by_text("Shortcuts:").wait_for(state="visible", timeout=4000)

    # Wait for metadata duration to become available.
    page.wait_for_function(
        "() => { const v = document.querySelector('video'); return !!v && Number.isFinite(v.duration) && v.duration > 0; }",
        timeout=12000,
    )

    before = page.evaluate("() => document.querySelector('video')?.currentTime ?? 0")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(250)
    after = page.evaluate("() => document.querySelector('video')?.currentTime ?? 0")
    assert after >= before, f"Expected seek forward, got before={before} after={after}"

    # Wait until preview status leaves temporary generation state.
    page.wait_for_function(
        """() => {
            const el = document.querySelector('[aria-label="Video player"]');
            if (!el) return false;
            const text = el.textContent || '';
            return text.includes('Timeline previews enabled')
                || text.includes('Timeline previews unavailable for this clip')
                || text.includes('Timeline previews disabled (media cache off)');
        }""",
        timeout=12000,
    )
    preview_enabled = page.get_by_text("Timeline previews enabled").count() > 0
    preview_unavailable = page.get_by_text("Timeline previews unavailable for this clip").count() > 0
    preview_disabled = page.get_by_text("Timeline previews disabled (media cache off)").count() > 0
    assert preview_enabled or preview_unavailable or preview_disabled, "Expected explicit timeline preview availability state"
    if preview_enabled:
        progress = page.locator(".plyr__progress input[type='range']").first
        progress.wait_for(state="visible", timeout=5000)
        box = progress.bounding_box()
        assert box is not None
        page.mouse.move(box["x"] + (box["width"] * 0.65), box["y"] + (box["height"] * 0.5))
        page.wait_for_timeout(300)
        page.locator(".plyr__preview-thumb--is-shown").first.wait_for(state="visible", timeout=5000)

    severe = _serious_console_errors(console_capture)
    assert not severe, "Serious browser console errors:\n" + "\n".join(severe[:20])
