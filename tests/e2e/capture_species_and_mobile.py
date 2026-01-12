import pytest
from playwright.sync_api import sync_playwright
import time
import os

# Output paths
ROOT_DIR = "/config/workspace/YA-WAMF"
DOCS_IMG_DIR = os.path.join(ROOT_DIR, "docs", "images")

def capture_more_screenshots():
    print("\nConnecting to Playwright service...")
    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        
        # --- Species Modal (Desktop) ---
        print("Capturing Species Modal (Desktop)...")
        context = browser.new_context(
            viewport={"width": 1400, "height": 900},
            device_scale_factor=2,
            color_scheme='dark'
        )
        page = context.new_page()
        page.goto("http://yawamf-frontend/species")
        page.wait_for_load_state("domcontentloaded")
        time.sleep(3)
        
        # Try finding a card with role="button"
        card = page.locator('div[role="button"]').first
        if card.count() > 0:
            print(" - Clicking species card...")
            card.click()
            
            # Wait for modal
            modal = page.locator('div[role="dialog"]')
            modal.wait_for(state="visible", timeout=5000)
            time.sleep(2)
            
            page.screenshot(path=os.path.join(DOCS_IMG_DIR, "species_details_modal.png"))
            print(" - Saved species_details_modal.png")
        else:
            print(" - No species cards found.")
            
        context.close()
        
        # --- Mobile Event Details ---
        print("\nCapturing Event Details (Mobile)...")
        context_mobile = browser.new_context(
            viewport={"width": 390, "height": 844},
            device_scale_factor=3,
            color_scheme='dark',
             user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/15.0 Mobile/15E148 Safari/604.1"
        )
        mobile_page = context_mobile.new_page()
        mobile_page.goto("http://yawamf-frontend/events")
        mobile_page.wait_for_load_state("domcontentloaded")
        time.sleep(3)
        
        card = mobile_page.locator('div[role="button"]').first
        if card.count() > 0:
            print(" - Clicking event card on mobile...")
            card.click()
            
            modal = mobile_page.locator('div[role="dialog"]')
            modal.wait_for(state="visible", timeout=5000)
            time.sleep(2)
            
            mobile_page.screenshot(path=os.path.join(DOCS_IMG_DIR, "event_details_mobile.png"))
            print(" - Saved event_details_mobile.png")
        
        context_mobile.close()
        browser.close()

if __name__ == "__main__":
    capture_more_screenshots()
