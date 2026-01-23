import os
import sys
from playwright.sync_api import sync_playwright

def inspect_ui():
    print("Connecting to Playwright service at ws://playwright-service:3000/...")
    with sync_playwright() as p:
        try:
            # Connect to the remote browser
            browser = p.chromium.connect("ws://playwright-service:3000/")
            context = browser.new_context(viewport={"width": 1280, "height": 800})
            page = context.new_page()
            
            page.emulate_media(color_scheme="dark")
            url = "http://172.19.0.15"
            print(f"Navigating to {url} in DARK MODE...")
            page.goto(url, wait_until="load", timeout=60000)
            
            # Click the Log In button
            login_btn = page.get_by_role("button", name="Log In")
            if login_btn.is_visible():
                login_btn.click()
                page.wait_for_timeout(2000)
                page.screenshot(path="tests/e2e/screenshots/login_page_dark.png")
                print("Dark Mode Login page screenshot saved.")

            browser.close()
            print("Inspection complete.")
        except Exception as e:
            print(f"Error during inspection: {e}")
            sys.exit(1)

if __name__ == "__main__":
    inspect_ui()
