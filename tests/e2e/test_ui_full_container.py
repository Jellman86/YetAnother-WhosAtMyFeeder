import pytest
from playwright.sync_api import sync_playwright
import os

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service at ws://playwright-service:3000/...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect("ws://playwright-service:3000/")
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

def test_full_system_ui(page):
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard: {base_url}")
    page.goto(base_url, timeout=30000)
    
    # Wait for DOM content instead of networkidle due to SSE connection
    page.wait_for_load_state("domcontentloaded")
    
    # Wait for the logo or some main text to appear
    page.wait_for_selector("text=WhosAtMyFeeder", timeout=10000)
    
    # 1. Verify Title
    print(f"Page Title: {page.title()}")
    
    # 2. Verify Dashboard Components
    print("Checking Dashboard components...")
    page.screenshot(path="dashboard_load.png")
    print("Screenshot saved: dashboard_load.png")

    # 3. Navigate to Explorer (Events)
    print("\n[2] Navigating to Explorer...")
    try:
        page.get_by_role("button", name="Explorer").click()
    except:
        page.get_by_text("Explorer").click()
        
    page.wait_for_url("**/events", timeout=10000)
    page.wait_for_load_state("domcontentloaded")
    print(f"Current URL: {page.url}")
    assert "/events" in page.url
    page.screenshot(path="explorer_page.png")

    # 4. Navigate to Leaderboard
    print("\n[3] Navigating to Leaderboard...")
    try:
        page.get_by_role("button", name="Leaderboard").click()
    except:
        page.get_by_text("Leaderboard").click()
        
    page.wait_for_url("**/species", timeout=10000)
    page.wait_for_load_state("domcontentloaded")
    print(f"Current URL: {page.url}")
    assert "/species" in page.url
    page.screenshot(path="leaderboard_page.png")
    
    # 5. Navigate to Settings
    print("\n[4] Navigating to Settings...")
    try:
        page.get_by_role("button", name="Settings").click()
    except:
        page.get_by_text("Settings").click()
        
    page.wait_for_url("**/settings", timeout=10000)
    page.wait_for_load_state("domcontentloaded")
    print(f"Current URL: {page.url}")
    assert "/settings" in page.url
    page.screenshot(path="settings_page.png")

    print("\n[SUCCESS] Full UI Test Completed Successfully.")