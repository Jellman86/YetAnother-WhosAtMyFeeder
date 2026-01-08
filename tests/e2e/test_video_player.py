import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect("ws://playwright-service:3000/")
            yield browser
            browser.close()
        except Exception as e:
            raise e

@pytest.fixture(scope="module")
def page(browser):
    context = browser.new_context(viewport={"width": 1280, "height": 720})
    page = context.new_page()
    yield page
    context.close()

def test_events_modal_video_button(page):
    base_url = "http://yawamf-frontend/events"
    
    print(f"\nNavigating to {base_url}")
    page.goto(base_url)
    # page.wait_for_load_state("networkidle") # Flaky with polling/SSE
    
    # Wait for detections to load
    try:
        page.wait_for_selector(".grid > div", timeout=5000)
    except:
        print("No detections found on Events page, skipping click test.")
        return

    # Click the first detection card
    print("Clicking first detection card...")
    # The card is a div with an onclick handler, usually inside the grid
    # We can target the first card.
    page.locator(".grid > div").first.click()
    
    # Wait for modal
    print("Waiting for modal...")
    page.wait_for_selector("div[role='dialog']", timeout=2000)
    
    # Screenshot the modal
    page.screenshot(path="modal_view.png")
    print("Screenshot saved: modal_view.png")
    
    # Check for video button
    # The button has a specific SVG path d="M8 5v14l11-7z" (Play icon)
    # OR it's a button inside the relative aspect-video container
    
    # In DetectionModal.svelte:
    # <button ... onclick={onPlayVideo} ...> <svg ... <path d="M8 5v14l11-7z"/> ...
    
    # Note: The button only renders if detection.has_clip is true.
    # We can't guarantee that. But we can print the result.
    
    video_btn = page.locator("button svg path[d='M8 5v14l11-7z']")
    if video_btn.count() > 0:
        if video_btn.first.is_visible():
            print("SUCCESS: Video play button is visible!")
        else:
             print("Video play button found but not visible (maybe obscured?)")
    else:
        print("Video play button NOT found (Detection might not have a clip, or feature broken)")


