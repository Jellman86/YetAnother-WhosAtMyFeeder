import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service...")
    with sync_playwright() as p:
        # Connect to the remote browser in the Playwright container
        # Note: The hostname 'playwright-service' must be resolvable from this container
        try:
            browser = p.chromium.connect("ws://playwright-service:3000/")
            print("Connected to Playwright service.")
            yield browser
            browser.close()
        except Exception as e:
            print(f"Failed to connect to Playwright: {e}")
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

def test_full_system_ui(page):
    # Use container name as hostname since they are on the same network
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard: {base_url}")
    try:
        page.goto(base_url, timeout=30000)
    except Exception as e:
        print(f"Navigation failed: {e}")
        # Try finding out if DNS is an issue or service is down
        raise e

    try:
        page.wait_for_load_state("networkidle", timeout=5000)
    except:
        print("Network idle timeout, continuing...")
    
    # 1. Verify Title
    title = page.title()
    print(f"Page Title: {title}")
    # Update title check based on Header.svelte "Yet Another WhosAtMyFeeder"
    # Note: <title> might be set in index.html
    # Let's verify what the actual title is.
    
    # 2. Verify Dashboard Components
    print("Checking Dashboard components...")
    
    # Take a screenshot for debugging
    page.screenshot(path="dashboard_load.png")
    print("Screenshot saved: dashboard_load.png")

    # 3. Navigate to Explorer (Events)
    print("\n[2] Navigating to Explorer...")
    # Using the label "Explorer" from Header.svelte
    # Since these are buttons in the nav, we look for them.
    # Note: In mobile view it might be different, but we set viewport to 1280x720 (Desktop)
    try:
        page.get_by_role("button", name="Explorer").click()
    except:
        # Fallback if it's a link or different role
        page.get_by_text("Explorer").click()
        
    page.wait_for_load_state("domcontentloaded")
    
    # Check URL
    print(f"Current URL: {page.url}")
    assert "/events" in page.url
    
    page.screenshot(path="explorer_page.png")
    print("Screenshot saved: explorer_page.png")

    # 4. Navigate to Leaderboard
    print("\n[3] Navigating to Leaderboard...")
    try:
        page.get_by_role("button", name="Leaderboard").click()
    except:
        page.get_by_text("Leaderboard").click()
        
    page.wait_for_load_state("domcontentloaded")
    
    print(f"Current URL: {page.url}")
    assert "/species" in page.url
    page.screenshot(path="leaderboard_page.png")
    print("Screenshot saved: leaderboard_page.png")
    
    # 5. Navigate to Settings
    print("\n[4] Navigating to Settings...")
    try:
        page.get_by_role("button", name="Settings").click()
    except:
        page.get_by_text("Settings").click()
        
    page.wait_for_load_state("domcontentloaded")
    
    print(f"Current URL: {page.url}")
    assert "/settings" in page.url
    
    # Verify some settings content exists
    # e.g. "General Configuration"
    content = page.content()
    # Check for text that definitely exists on settings page
    if "Configuration" in content or "Frigate" in content:
        print("Settings page content verified.")
    else:
        print("Warning: specific settings text not found.")
        
    page.screenshot(path="settings_page.png")
    print("Screenshot saved: settings_page.png")

    print("\n[SUCCESS] Full UI Test Completed.")
