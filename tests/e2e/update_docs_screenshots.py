import pytest
from playwright.sync_api import sync_playwright
import time
import os

# Output paths
ROOT_DIR = "/config/workspace/YA-WAMF"
DOCS_IMG_DIR = os.path.join(ROOT_DIR, "docs", "images")

def update_screenshots():
    print("\nConnecting to Playwright service at ws://playwright-service:3000/...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect("ws://playwright-service:3000/")
            print("Connected to Playwright service.")
            
            # --- Desktop Screenshots ---
            print("Capturing Desktop Screenshots (Dark Mode)...")
            context_desktop = browser.new_context(
                viewport={"width": 1400, "height": 900},
                device_scale_factor=2,  # High DPI for crisp screenshots
                color_scheme='dark'
            )
            page = context_desktop.new_page()
            
            # 1. Dashboard Preview (Root)
            print(" - Dashboard...")
            page.goto("http://yawamf-frontend/")
            page.wait_for_load_state("domcontentloaded")
            # Wait a bit for animations/SSE to settle
            time.sleep(2) 
            page.screenshot(path=os.path.join(ROOT_DIR, "dashboard-preview.png"))

            # 2. Events Page
            print(" - Events...")
            page.goto("http://yawamf-frontend/events")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            page.screenshot(path=os.path.join(DOCS_IMG_DIR, "frontend_events.png"))

            # 3. Species Page
            print(" - Species...")
            page.goto("http://yawamf-frontend/species")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            page.screenshot(path=os.path.join(DOCS_IMG_DIR, "frontend_species.png"))

            # 4. Settings Page
            print(" - Settings...")
            page.goto("http://yawamf-frontend/settings")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            page.screenshot(path=os.path.join(DOCS_IMG_DIR, "frontend_settings.png"))
            
            context_desktop.close()
            
            # --- Mobile Screenshots ---
            print("Capturing Mobile Screenshots (Dark Mode)...")
            context_mobile = browser.new_context(
                viewport={"width": 390, "height": 844},
                device_scale_factor=3,
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1",
                color_scheme='dark'
            )
            mobile_page = context_mobile.new_page()
            
            # 5. Mobile Dashboard
            print(" - Mobile Dashboard...")
            mobile_page.goto("http://yawamf-frontend/")
            mobile_page.wait_for_load_state("domcontentloaded")
            time.sleep(2)
            mobile_page.screenshot(path=os.path.join(DOCS_IMG_DIR, "dashboard-mobile.png"))

            context_mobile.close()
            browser.close()
            print("\n[SUCCESS] All screenshots updated.")
            
        except Exception as e:
            print(f"\n[ERROR] Failed to capture screenshots: {e}")
            raise e

if __name__ == "__main__":
    update_screenshots()
