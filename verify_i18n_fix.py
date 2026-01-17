
from playwright.sync_api import sync_playwright, expect

def run():
    with sync_playwright() as p:
        try:
            browser = p.chromium.connect("ws://playwright-service:3000")
            page = browser.new_page()
            page.goto("http://yawamf-frontend:80")
            
            # Wait for the main content to be visible, which indicates the app has loaded
            # beyond the white screen. We'll wait for the main content area.
            main_content = page.locator("#main-content")
            
            # Give it a generous timeout to be sure.
            expect(main_content).to_be_visible(timeout=15000)

            print("Successfully loaded page. The main content is visible.")
            page.screenshot(path="verify_i18n_fix.png")
            print("Screenshot saved to verify_i18n_fix.png")

            browser.close()
        except Exception as e:
            print(f"An error occurred: {e}")
            # Try to get a screenshot even if it fails
            try:
                page.screenshot(path="verify_i18n_fix_error.png")
                print("Error screenshot saved to verify_i18n_fix_error.png")
            except Exception as screenshot_e:
                print(f"Could not take error screenshot: {screenshot_e}")


if __name__ == "__main__":
    run()
