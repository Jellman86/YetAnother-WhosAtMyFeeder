import pytest
import os
from playwright.sync_api import sync_playwright

BASE_URL = "http://yawamf-frontend"


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
def mobile_page(browser):
    # Simulate an iPhone 13 viewport
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
        ignore_https_errors=True
    )
    page = context.new_page()
    yield page
    context.close()


def _is_login_page(page) -> bool:
    return page.locator("input#username").count() > 0


def _open_mobile_sidebar(page) -> None:
    # The mobile header in App.svelte always renders the sidebar toggle
    # as the first header button in vertical/mobile layout.
    header = page.locator("div.md\\:hidden.sticky.top-0")
    header.wait_for(timeout=10000)
    menu_button = header.locator("button").first
    menu_button.click(timeout=10000)
    page.locator("aside.translate-x-0 nav").first.wait_for(timeout=10000)


def _go_to_settings(page) -> None:
    _open_mobile_sidebar(page)
    # Settings can be absent in guest/public mode. Detect by gear icon path.
    settings_button = page.locator("aside nav button:has(path[d^='M10.325'])").first
    if settings_button.count() > 0 and settings_button.is_visible():
        settings_button.click(timeout=5000)
    else:
        page.goto(f"{BASE_URL}/settings", timeout=30000)


def test_mobile_layout(mobile_page):
    print(f"\n[1] Navigating to Dashboard (Mobile View): {BASE_URL}")
    try:
        mobile_page.goto(BASE_URL, timeout=30000)
    except Exception as e:
        print(f"Navigation failed: {e}")
        raise e

    # Wait for content to load (avoid networkidle due to SSE)
    mobile_page.wait_for_load_state("domcontentloaded")

    # If auth is enforced and public access is disabled, app loads login page.
    # In that mode we cannot test sidebar navigation without credentials.
    if _is_login_page(mobile_page):
        print("Login page detected (auth required without public access). Mobile smoke test stops here.")
        return

    mobile_page.locator("main#main-content").wait_for(timeout=10000)
    
    print("Taking mobile dashboard screenshot...")
    mobile_page.screenshot(path="mobile_dashboard.png")
    
    print("Opening mobile menu and navigating to Events...")
    _open_mobile_sidebar(mobile_page)
    nav_buttons = mobile_page.locator("aside nav button.nav-button")
    nav_count = nav_buttons.count()
    assert nav_count >= 3, f"Expected at least 3 sidebar nav buttons, found {nav_count}"
    nav_buttons.nth(1).click(timeout=5000)
    mobile_page.wait_for_url("**/events", timeout=10000)
    assert "/events" in mobile_page.url

    print("Navigating to Settings (or validating auth redirect)...")
    _go_to_settings(mobile_page)
    mobile_page.wait_for_load_state("domcontentloaded")

    print("Taking mobile settings screenshot...")
    mobile_page.screenshot(path="mobile_settings.png")

    # If auth is enabled with public access, /settings may be blocked and
    # redirect to login (or back to home).
    if "/settings" not in mobile_page.url:
        assert _is_login_page(mobile_page) or mobile_page.url.endswith("/")
        print("Settings route blocked by auth/public mode as expected.")
        return
    
    # 4. Verify Settings Layout
    print("Verifying settings content...")
    mobile_page.wait_for_selector("h2, h3", timeout=10000)
    
    print("\n[SUCCESS] Mobile UI Test Completed Successfully.")
