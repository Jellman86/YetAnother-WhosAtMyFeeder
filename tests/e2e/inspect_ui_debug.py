from playwright.sync_api import sync_playwright

def run():
    with sync_playwright() as p:
        print("Connecting to Playwright...")
        browser = p.chromium.connect("ws://playwright-service:3000/")
        page = browser.new_page()
        
        # 1. Dashboard
        print("Navigating to Dashboard...")
        page.goto("http://yawamf-frontend/", wait_until="domcontentloaded")
        page.wait_for_timeout(2000) # Wait for hydration
        page.screenshot(path="dashboard_debug.png")
        with open("dashboard.html", "w") as f:
            f.write(page.content())
        print("Captured Dashboard.")

        # 2. Settings
        print("Navigating to Settings...")
        page.goto("http://yawamf-frontend/settings", wait_until="domcontentloaded")
        page.wait_for_timeout(2000)
        page.screenshot(path="settings_debug.png")
        with open("settings.html", "w") as f:
            f.write(page.content())
        print("Captured Settings.")
        
        # 3. Accessibility Check
        print("Checking for Accessibility tab...")
        try:
            # Try to find a link or button with "Accessibility" or "Access"
            a11y = page.get_by_text("Accessibility")
            if a11y.count() > 0:
                print("Found 'Accessibility' text. Clicking...")
                a11y.first.click()
                page.wait_for_timeout(1000)
                page.screenshot(path="accessibility_debug.png")
                with open("accessibility.html", "w") as f:
                    f.write(page.content())
            else:
                print("❌ 'Accessibility' text NOT FOUND on Settings page.")
        except Exception as e:
            print(f"Error checking accessibility: {e}")

        browser.close()

if __name__ == "__main__":
    run()
