
import time
from playwright.sync_api import sync_playwright, expect

def run():
    retries = 3
    for i in range(retries):
        try:
            print(f"Attempt {i+1} of {retries}...")
            # Wait for the frontend container to build and start
            print("Waiting 30 seconds for the frontend to build...")
            time.sleep(30)

            with sync_playwright() as p:
                browser = p.chromium.connect("ws://playwright-service:3000")
                page = browser.new_page()
                page.goto("http://yawamf-frontend:80")
                
                main_content = page.locator("#main-content")
                expect(main_content).to_be_visible(timeout=15000)

                print("Successfully loaded page. The main content is visible.")
                page.screenshot(path="verify_i18n_fix.png")
                print("Screenshot saved to verify_i18n_fix.png")

                browser.close()
                # If successful, break the loop
                break
        except Exception as e:
            print(f"An error occurred on attempt {i+1}: {e}")
            if i < retries - 1:
                print("Retrying...")
            else:
                print("All retries failed.")
                # Try to get a screenshot even if it fails
                try:
                    with sync_playwright() as p:
                        browser = p.chromium.connect("ws://playwright-service:3000")
                        page = browser.new_page()
                        page.goto("http://yawamf-frontend:80")
                        page.screenshot(path="verify_i18n_fix_error.png")
                        print("Error screenshot saved to verify_i18n_fix_error.png")
                        browser.close()
                except Exception as screenshot_e:
                    print(f"Could not take error screenshot: {screenshot_e}")

if __name__ == "__main__":
    run()
