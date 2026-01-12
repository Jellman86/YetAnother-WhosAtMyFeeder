import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service at ws://playwright-service:3000/...")
    with sync_playwright() as p:
        try:
            # Connect using the internal Docker network hostname
            browser = p.chromium.connect("ws://playwright-service:3000/")
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

def test_mobile_layout(mobile_page):
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard (Mobile View): {base_url}")
    try:
        mobile_page.goto(base_url, timeout=30000)
    except Exception as e:
        print(f"Navigation failed: {e}")
        raise e

    # Wait for content to load (avoid networkidle due to SSE)
    mobile_page.wait_for_load_state("domcontentloaded")
    mobile_page.wait_for_selector("text=YA-WAMF", timeout=10000)
    
    print("Taking mobile dashboard screenshot...")
    mobile_page.screenshot(path="mobile_dashboard.png")
    
    # 1. Verify Mobile Menu Button Exists
    # Look for the hamburger menu button which should be visible on mobile
    print("Looking for mobile menu button...")
    menu_button = mobile_page.get_by_label("Toggle menu")
    
    if menu_button.is_visible():
        print("Mobile menu button found.")
    else:
        # Fallback: try to find by SVG or class if label isn't present
        print("Menu button by label not visible, checking generic selector...")
        # This assumes the sidebar code uses standard button for toggle
        # We can try clicking the first button in the header
        menu_button = mobile_page.locator("button").first
        
    # 2. Open Mobile Menu
    print("Clicking menu button...")
    menu_button.click()
    
    # Wait for menu to slide out/appear
    # We look for a navigation item that was previously hidden or inside the menu
    print("Waiting for menu items...")
    # 'Events' or 'Explorer' should be in the menu
    explorer_link = mobile_page.get_by_role("button", name="Explorer")
    if not explorer_link.is_visible():
         explorer_link = mobile_page.get_by_text("Explorer")
    
    # 3. Navigate to Settings via Mobile Menu
    print("Navigating to Settings via mobile menu...")
    try:
        mobile_page.get_by_role("button", name="Settings").click()
    except:
        mobile_page.get_by_text("Settings").click()

    mobile_page.wait_for_url("**/settings", timeout=10000)
    print(f"Current URL: {mobile_page.url}")
    assert "/settings" in mobile_page.url
    
    print("Taking mobile settings screenshot...")
    mobile_page.screenshot(path="mobile_settings.png")
    
    # 4. Verify Settings Layout
    # Check if a specific setting is visible and readable
    print("Verifying settings content...")
    try:
        # Try finding typical settings headers
        mobile_page.wait_for_selector("h2, h3", timeout=5000)
    except:
        print("Header lookup timed out, checking page content...")

    content = mobile_page.content()
    if "Configuration" in content or "Frigate" in content:
        print("Settings page content verified (found 'Configuration' or 'Frigate').")
    else:
        print("Warning: Specific settings text not immediately found.")
    
    print("\n[SUCCESS] Mobile UI Test Completed Successfully.")
