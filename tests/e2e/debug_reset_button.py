import os
import sys
from playwright.sync_api import sync_playwright

def debug_reset():
    print("Connecting to Playwright...")
    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1280, "height": 800})
        page = context.new_page()
        
        # Enable console logging
        page.on("console", lambda msg: print(f"CONSOLE: {msg.type}: {msg.text}"))
        page.on("pageerror", lambda err: print(f"PAGE ERROR: {err}"))
        
        url = "http://172.19.0.15" # Using container IP
        print(f"Navigating to {url}...")
        page.goto(url, wait_until="load", timeout=60000)
        
        # Navigate to Settings
        print("Clicking Settings...")
        page.get_by_role("button", name="Settings").click()
        page.wait_for_url("**/settings")
        
        # Navigate to Data tab
        print("Clicking Data tab...")
        # Note: Tab text might be translated, looking for "Data" or checking DOM
        # "Data" key is settings.tabs.data -> "Data" (en)
        # Using selector to be safe
        page.locator("button.tab-button").filter(has_text="Data").click()
        
        # Find Reset Button
        reset_btn = page.locator("button[aria-label='Reset Database & Cache']")
        if not reset_btn.is_visible():
             # Try finding by text if aria-label is translated differently
             reset_btn = page.get_by_text("Reset Database & Cache")
        
        if reset_btn.is_visible():
            print("Reset button FOUND.")
            
            # Setup dialog handler
            def handle_dialog(dialog):
                print(f"DIALOG OPENED: {dialog.message}")
                dialog.accept()
                
            page.on("dialog", handle_dialog)
            
            print("Clicking Reset button...")
            reset_btn.click()
            
            # Wait a bit for reaction
            page.wait_for_timeout(3000)
        else:
            print("Reset button NOT FOUND.")
            page.screenshot(path="tests/e2e/screenshots/debug_data_tab.png")
            
        browser.close()

if __name__ == "__main__":
    debug_reset()
