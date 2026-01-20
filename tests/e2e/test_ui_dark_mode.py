import os
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="module")
def browser():
    ws_url = os.environ.get("PLAYWRIGHT_WS", "ws://playwright-service:3000/")
    print(f"\nConnecting to Playwright service at {ws_url}...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect(ws_url)
            print("Connected to Playwright service.")
            yield browser
            browser.close()
        except Exception as e:
            print(f"Failed to connect to Playwright service: {e}")
            raise e

@pytest.fixture(scope="module")
def page(browser):
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True
    )
    page = context.new_page()
    yield page
    context.close()

def test_dark_mode_ui(page):
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard: {base_url}")
    page.goto(base_url, timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    
    # 1. Switch to Dark Mode (if not already)
    # Check if html has class 'dark'
    is_dark = page.evaluate("document.documentElement.classList.contains('dark')")
    
    if not is_dark:
        print("Switching to Dark Mode...")
        # Click the theme toggle button in header
        # The button has an SVG and a title attribute 'Switch to dark mode'
        try:
            page.get_by_title("Switch to dark mode").click()
        except Exception:
            try:
                page.get_by_role("button", name="Dark").first.click()
            except Exception:
                # Fallback locator if title text varies
                page.locator("button svg path[d*='M20.354']").locator("..").locator("..").first.click()
            
        page.wait_for_timeout(500) # Wait for transition
        
    # Verify dark mode applied
    assert page.evaluate("document.documentElement.classList.contains('dark')")
    
    # 2. Capture Dashboard Dark Mode
    print("Taking dark mode dashboard screenshot...")
    page.screenshot(path="dashboard_dark.png")
    
    # 3. Check Contrast of Cards
    # We check if any cards exist before attempting to read styles
    card_count = page.locator(".card-base").count()
    if card_count > 0:
        card_bg = page.locator(".card-base").first.evaluate("el => getComputedStyle(el).backgroundColor")
        print(f"Card Background Color: {card_bg}")
        # Expected: rgba(30, 41, 59, 0.8) which is slate-800 with 80% opacity
    else:
        print("Note: No detection cards found to test contrast.")
    
    body_bg = page.locator("body").first.evaluate("el => getComputedStyle(el).backgroundColor")
    print(f"Body Background Color: {body_bg}")
    # Expected: rgb(2, 6, 23) which is surface-dark (slate-950)

    # 4. Navigate to Events
    print("\n[2] Navigating to Events...")
    try:
        page.get_by_role("button", name="Explorer").click()
    except:
        page.get_by_text("Explorer").click()
        
    page.wait_for_url("**/events")
    page.wait_for_load_state("domcontentloaded")
    
    print("Taking dark mode explorer screenshot...")
    page.screenshot(path="explorer_dark.png")

    print("\n[SUCCESS] Dark Mode Test Completed.")
