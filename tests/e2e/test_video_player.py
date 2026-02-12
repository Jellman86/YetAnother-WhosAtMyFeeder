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
        r"Failed to load resource: the server responded with a status of 403",
        r"Failed to load initial detections AbortError",
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
        play_button = page.get_by_role("button", name=re.compile(r"^Play video"))
        if play_button.count() > 0 and play_button.first.is_visible():
            return True
        page.keyboard.press("Escape")
        page.wait_for_timeout(150)
    return False


def _click_play_button_in_open_detection_modal(page: Page) -> None:
    # Scope lookup to the currently open detection modal so we never hit
    # background card play buttons.
    modal_play = page.locator("div[role='dialog'] button[aria-label^='Play video']").first
    if modal_play.count() > 0 and modal_play.is_visible():
        modal_play.click(force=True, timeout=8000)
        return

    # Fallback for markup changes.
    page.get_by_role("button", name=re.compile(r"^Play video")).first.click(force=True, timeout=8000)


def _playback_status_chip(page: Page):
    return page.locator("div[role='dialog'] div.flex.items-center.gap-1\\.5.shrink-0 > span").first


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
    _click_play_button_in_open_detection_modal(page)
    player = page.get_by_label("Video player")
    player.wait_for(state="visible", timeout=8000)
    page.get_by_label("Close video").wait_for(state="visible", timeout=4000)

    # If clip is unavailable in this dataset, skip timeline assertions.
    unavailable = page.get_by_text("Video Unavailable").count() > 0 or page.get_by_text("Clip Fetching Disabled").count() > 0
    if unavailable:
        pytest.skip("Clip unavailable in current environment; UI opened but timeline controls not testable")

    page.locator("video").first.wait_for(state="visible", timeout=8000)
    plyr_visible = page.locator(".plyr").first.is_visible() if page.locator(".plyr").count() > 0 else False
    controls_visible = page.locator(".plyr__controls").first.is_visible() if page.locator(".plyr__controls").count() > 0 else False
    assert plyr_visible or controls_visible or page.locator("video").count() > 0, "Expected video UI (Plyr or native fallback) to be visible"
    shortcuts_hint = page.locator("span", has_text=re.compile(r"play/pause|Keyboard shortcuts", re.IGNORECASE)).first
    shortcuts_hint.wait_for(state="visible", timeout=4000)

    # Wait for metadata duration to become available.
    page.wait_for_function(
        "() => { const v = document.querySelector('video'); return !!v && Number.isFinite(v.duration) && v.duration > 0; }",
        timeout=12000,
    )

    # Playback state chip should not stay stuck on "Paused" while media is actively playing.
    page.evaluate("() => { const v = document.querySelector('video'); return v ? v.play() : null; }")
    page.wait_for_timeout(250)
    playback_snapshot = page.evaluate(
        "() => { const v = document.querySelector('video'); return v ? { paused: v.paused, ended: v.ended, t: v.currentTime } : null; }"
    )
    if playback_snapshot and not playback_snapshot["paused"] and not playback_snapshot["ended"]:
        chip_class = _playback_status_chip(page).get_attribute("class") or ""
        assert "bg-cyan-400/15" not in chip_class, (
            f"Playback status chip appears stuck in paused style while video is playing: "
            f"state={playback_snapshot} class={chip_class}"
        )

    before = page.evaluate("() => document.querySelector('video')?.currentTime ?? 0")
    page.keyboard.press("ArrowRight")
    page.wait_for_timeout(250)
    after = page.evaluate("() => document.querySelector('video')?.currentTime ?? 0")
    assert after >= before, f"Expected seek forward, got before={before} after={after}"

    # Wait until preview status leaves temporary generation state.
    page.wait_for_function(
        """() => {
            const el = document.querySelector('[aria-label*="Timeline previews"]');
            if (!el) return false;
            const label = el.getAttribute('aria-label') || '';
            return label.includes('Timeline previews enabled')
                || label.includes('Timeline previews unavailable for this clip')
                || label.includes('Timeline previews disabled (media cache off)');
        }""",
        timeout=12000,
    )
    labels = page.locator('[aria-label*="Timeline previews"]').all_inner_texts()
    aria_labels = [
        page.locator('[aria-label*="Timeline previews"]').nth(i).get_attribute("aria-label") or ""
        for i in range(page.locator('[aria-label*="Timeline previews"]').count())
    ]
    preview_enabled = any("Timeline previews enabled" in v for v in aria_labels + labels)
    preview_unavailable = any("Timeline previews unavailable for this clip" in v for v in aria_labels + labels)
    preview_disabled = any("Timeline previews disabled (media cache off)" in v for v in aria_labels + labels)
    assert preview_enabled or preview_unavailable or preview_disabled, "Expected explicit timeline preview availability state"
    if preview_enabled:
        progress = page.locator(".plyr__progress input[type='range']").first
        # Preview UI can be disabled by safety fallback even when the probe succeeded.
        # In that case playback should still be healthy and we skip hover-thumbnail assertion.
        if progress.is_visible():
            box = progress.bounding_box()
            assert box is not None
            page.mouse.move(box["x"] + (box["width"] * 0.65), box["y"] + (box["height"] * 0.5))
            page.wait_for_timeout(300)
            page.locator(".plyr__preview-thumb--is-shown").first.wait_for(state="visible", timeout=5000)

    severe = _serious_console_errors(console_capture)
    assert not severe, "Serious browser console errors:\n" + "\n".join(severe[:20])
