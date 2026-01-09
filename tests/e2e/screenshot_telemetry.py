#!/usr/bin/env python3
"""
Screenshot the telemetry banner using the Playwright service.
This creates a fresh browser context to ensure the banner is visible.
"""
from playwright.sync_api import sync_playwright
import time

def main():
    with sync_playwright() as p:
        print("Connecting to Playwright service...")
        browser = p.chromium.connect("ws://playwright-service:3000/")

        # Create fresh context with no localStorage (simulates first-time user)
        context = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="en-US"
        )
        page = context.new_page()

        try:
            print("Navigating to YA-WAMF frontend...")
            # Use the internal container hostname
            page.goto("http://yawamf-frontend/", wait_until="networkidle", timeout=30000)

            print("Waiting for page to load...")
            time.sleep(3)  # Give it time for settings to load

            # Check if banner is visible
            try:
                banner = page.locator('text=Help improve YA-WAMF')
                is_visible = banner.is_visible(timeout=5000)

                if is_visible:
                    print("✓ Telemetry banner is visible!")
                else:
                    print("✗ Banner element found but not visible")
            except Exception as e:
                print(f"✗ Banner not found: {e}")

            # Take full page screenshot
            screenshot_path = "/config/workspace/YA-WAMF/telemetry_banner_screenshot.png"
            page.screenshot(path=screenshot_path, full_page=True)
            print(f"✓ Screenshot saved: {screenshot_path}")

            # Also take a viewport-only screenshot
            viewport_path = "/config/workspace/YA-WAMF/telemetry_banner_viewport.png"
            page.screenshot(path=viewport_path, full_page=False)
            print(f"✓ Viewport screenshot saved: {viewport_path}")

        except Exception as e:
            print(f"Error: {e}")
            import traceback
            traceback.print_exc()
        finally:
            context.close()
            browser.close()
            print("Done!")

if __name__ == "__main__":
    main()
