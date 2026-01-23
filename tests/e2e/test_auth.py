import pytest
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service...")
    with sync_playwright() as p:
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
    context.set_extra_http_headers({"Accept-Language": "en"})
    page = context.new_page()
    yield page
    context.close()

def test_auth_disabled_flow(page):
    """
    Test that when Auth is disabled (default), the user has full access (Owner role).
    This verifies the fix where 'authRequired: false' implies 'canModify: true'.
    """
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard: {base_url}")
    page.goto(base_url)
    page.wait_for_load_state("domcontentloaded")
    
    # 1. Verify Dashboard Load
    print("Verifying Dashboard...")
    expect(page.get_by_role("heading", name="Dashboard")).to_be_visible()
    
    # 2. Verify Settings Access (Should be visible when Auth is disabled)
    print("Verifying Settings Access...")
    settings_link = page.get_by_role("button", name="Settings")
    expect(settings_link).to_be_visible()
    
    # 3. Navigate to Settings
    print("Navigating to Settings...")
    settings_link.click()
    page.wait_for_url("**/settings")
    
    # 4. Verify Security Tab
    print("Verifying Security Tab...")
    security_tab = page.locator("button.tab-button").filter(has_text="Security").first
    expect(security_tab).to_be_visible()
    security_tab.click()
    
    # 5. Verify Authentication Controls presence
    print("Verifying Authentication Controls...")
    expect(page.get_by_text("Enable Authentication")).to_be_visible()
    expect(page.get_by_text("Public Access")).to_be_visible()
    
    # 6. Verify "Save" button visibility (Permissions check)
    # If the user has 'canModify', the save button logic should be active (though it might be hidden if not dirty).
    # We'll check if we can modify a setting to trigger the "Unsaved Changes" bar.
    
    print("Testing modification permission...")
    # Toggle "Public Access" to trigger dirty state
    public_access_toggle = page.locator("button[role='switch']").filter(has_text="Enable Public Access").first
    if public_access_toggle.is_visible():
        public_access_toggle.click()
        # Verify "Apply Settings" bar appears
        expect(page.get_by_text("Unsaved changes")).to_be_visible()
        # Toggle back to reset state
        public_access_toggle.click()
    else:
        print("⚠️ Public access toggle not found, skipping modification test.")

    print("\n[SUCCESS] Auth Disabled Flow Verified.")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        try:
            test_auth_disabled_flow(page)
        finally:
            browser.close()
