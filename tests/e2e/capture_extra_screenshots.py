import pytest
from playwright.sync_api import sync_playwright
import time
import os

# Output paths
ROOT_DIR = "/config/workspace/YA-WAMF"
DOCS_IMG_DIR = os.path.join(ROOT_DIR, "docs", "images")

def capture_extra_screenshots():
    print("\nConnecting to Playwright service at ws://playwright-service:3000/...")
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect("ws://playwright-service:3000/")
            print("Connected to Playwright service.")
            
            # --- Desktop Screenshots ---
            print("Capturing Event Details Modal (Dark Mode)...")
            context = browser.new_context(
                viewport={"width": 1400, "height": 900},
                device_scale_factor=2,  # High DPI
                color_scheme='dark'
            )
            page = context.new_page()
            
            # 1. Event Details Modal
            print(" - Navigating to Events...")
            page.goto("http://yawamf-frontend/events")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3) # Wait for cards to load and stabilize
            
            # Find the first card and click it
            # We look for something that looks like a card. The DetectionCard has role="button"
            card = page.locator('div[role="button"]').first
            
            if card.count() > 0:
                print(" - Clicking first event card...")
                card.click()
                
                # Wait for modal
                print(" - Waiting for modal...")
                modal = page.locator('div[role="dialog"]')
                modal.wait_for(state="visible", timeout=5000)
                
                # Wait for animations
                time.sleep(2)
                
                # Screenshot
                screenshot_path = os.path.join(DOCS_IMG_DIR, "event_details_modal.png")
                page.screenshot(path=screenshot_path)
                print(f" - Saved to {screenshot_path}")
                
                # Close modal to be clean (optional)
                page.keyboard.press("Escape")
                time.sleep(1)
            else:
                print(" [WARNING] No event cards found. Skipping modal screenshot.")

            # 2. Species Details Modal (if possible)
            # This is harder to guarantee without knowing valid species, but we can try the Species page
            print(" - Navigating to Species...")
            page.goto("http://yawamf-frontend/species")
            page.wait_for_load_state("domcontentloaded")
            time.sleep(3)
            
            # Click first species card (assuming they are buttons or have click handlers)
            # The Species page logic needs checking, but usually cards are clickable
            species_card = page.locator('.cursor-pointer').first 
            
            if species_card.count() > 0:
                print(" - Clicking first species card...")
                species_card.click()
                
                # Wait for modal
                # The SpeciesDetailModal might also be a dialog
                modal = page.locator('div[role="dialog"]')
                try:
                    modal.wait_for(state="visible", timeout=5000)
                    time.sleep(2)
                    screenshot_path = os.path.join(DOCS_IMG_DIR, "species_details_modal.png")
                    page.screenshot(path=screenshot_path)
                    print(f" - Saved to {screenshot_path}")
                except:
                    print(" [WARNING] Species modal did not appear or timed out.")
            else:
                 print(" [WARNING] No species cards found.")


            context.close()
            browser.close()
            print("\n[SUCCESS] Extra screenshots captured.")
            
        except Exception as e:
            print(f"\n[ERROR] Failed to capture screenshots: {e}")
            raise e

if __name__ == "__main__":
    capture_extra_screenshots()
