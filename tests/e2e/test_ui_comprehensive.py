import pytest
import re
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service...")
    with sync_playwright() as p:
        try:
            # Connect to the remote browser in the Playwright container
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
    # Set English as default locale
    context.set_extra_http_headers({"Accept-Language": "en"})
    
    page = context.new_page()
    
    # Capture console logs to see the "Dirty Setting" messages
    page.on("console", lambda msg: print(f"BROWSER_CONSOLE: {msg.type}: {msg.text}"))
    page.on("pageerror", lambda err: print(f"BROWSER_ERROR: {err}"))
    
    yield page
    context.close()

def test_ui_comprehensive(page):
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard: {base_url}")
    page.goto(base_url, timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    
    # 1. Verify Navigation and Basic Layout
    print("Verifying Navigation...")
    expect(page.get_by_role("button", name="Explorer")).to_be_visible()
    expect(page.get_by_role("button", name="Leaderboard")).to_be_visible()
    expect(page.get_by_role("button", name="Settings")).to_be_visible()
    
    # 2. Dark Mode Toggle
    print("Testing Dark Mode Toggle...")
    html = page.locator("html")
    initial_dark = "dark" in (html.get_attribute("class") or "")
    
    def get_theme_toggle():
        # Try Desktop Sidebar (Text)
        btn = page.get_by_text("Dark Mode", exact=True)
        if btn.is_visible(): return btn
        btn = page.get_by_text("Light Mode", exact=True)
        if btn.is_visible(): return btn
        # Try Collapsed Sidebar (Title)
        btn = page.get_by_title(re.compile(r"Switch to (dark|light) mode", re.I))
        if btn.is_visible(): return btn
        # Try Mobile Header
        btn = page.locator(".md\\:hidden button").first
        if btn.is_visible(): return btn
        return None

    toggle_btn = get_theme_toggle()
    if toggle_btn:
        print(f"Clicking theme toggle (Initial dark: {initial_dark})...")
        toggle_btn.click()
        page.wait_for_timeout(1000)
        
        after_toggle_dark = "dark" in (html.get_attribute("class") or "")
        print(f"✅ Dark mode toggle clicked. Class state: {initial_dark} -> {after_toggle_dark}")
        
        # Re-locate for restore click because text/title might have changed
        toggle_btn = get_theme_toggle()
        if toggle_btn:
            print("Restoring theme...")
            toggle_btn.click()
            page.wait_for_timeout(1000)
    else:
        print("⚠️ Theme toggle button not found. Skipping toggle test.")

    # 3. Settings Depth and "Apply Settings" Bug Debugging
    print("\n[2] Navigating to Settings...")
    page.get_by_role("button", name="Settings").click()
    page.wait_for_url("**/settings")
    page.wait_for_load_state("domcontentloaded")
    
    # Use class-based selector for tabs to ensure we only target the actual tabs
    def get_settings_tab(name):
        # The SettingsTabs component uses class "tab-button"
        return page.locator("button.tab-button").filter(has_text=name).first

    # Check tabs
    tabs = ["Connection", "Detection", "Notifications", "Integrations", "Data", "Appearance", "Accessibility"]
    for tab in tabs:
        btn = get_settings_tab(tab)
        expect(btn).to_be_visible()
    
    # DEBUG: Trigger "Apply Settings" button
    print("\n[3] Debugging 'Apply Settings' button visibility...")
    # Ensure we are on Connection tab
    get_settings_tab("Connection").click()
    
    # Change Frigate URL slightly
    frigate_url_input = page.locator("#frigate-url")
    frigate_url_input.wait_for(state="visible")
    original_url = frigate_url_input.input_value()
    print(f"Original Frigate URL: {original_url}")
    
    # Modify
    new_url = original_url + "/" if not original_url.endswith("/") else original_url[:-1]
    print(f"Setting Frigate URL to: {new_url}")
    frigate_url_input.fill(new_url) 
    # Trigger blur to ensure change is registered
    frigate_url_input.blur() 
    page.wait_for_timeout(2000) # Wait longer for reactivity
    
    print("Checking if 'Apply Settings' button is visible...")
    # The button has text "Apply Settings"
    apply_btn = page.get_by_role("button", name="Apply Settings")
    
    if apply_btn.is_visible():
        print("✅ Success: 'Apply Settings' button appeared after modification.")
    else:
        print("❌ FAILURE: 'Apply Settings' button is MISSING after modification!")
        # Take a screenshot
        page.screenshot(path="settings_button_missing_debug.png")
        
        # Maybe it's a different tab? Let's try changing a checkbox
        print("Trying to toggle a checkbox to see if it triggers dirty state...")
        get_settings_tab("Detection").click()
        page.wait_for_timeout(500)
        
        # Find "Auto Video Analysis" toggle
        video_analysis_row = page.locator("div").filter(has_text="Auto Video Analysis").last
        toggle = video_analysis_row.get_by_role("button")
        if toggle.is_visible():
            toggle.click()
            page.wait_for_timeout(1000)
            if apply_btn.is_visible():
                print("✅ Success: 'Apply Settings' button appeared after toggling Video Analysis.")
            else:
                print("❌ Still missing after checkbox toggle.")
        else:
            print("⚠️ Video Analysis toggle not found.")
    
    # 4. Accessibility deep link test
    print("\n[4] Testing Accessibility Deep Link...")
    get_settings_tab("Accessibility").click()
    page.wait_for_timeout(500)
    expect(page.get_by_text("High Contrast", exact=True)).to_be_visible()
    print("✅ Accessibility tab content visible.")
    
    # Verify hash update
    print(f"Current URL hash: {page.evaluate('window.location.hash')}")
    assert "#accessibility" in page.url
    
    # Revert Frigate URL if changed
    if original_url:
        get_settings_tab("Connection").click()
        frigate_url_input.fill(original_url)
        frigate_url_input.blur()
        page.wait_for_timeout(1000)

    print("\n[SUCCESS] Comprehensive UI Test Completed.")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1280, "height": 720})
        page = context.new_page()
        page.on("console", lambda msg: print(f"BROWSER_CONSOLE: {msg.type}: {msg.text}"))
        try:
            test_ui_comprehensive(page)
        finally:
            browser.close()