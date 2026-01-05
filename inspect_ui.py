from playwright.sync_api import sync_playwright

def main():
    print("Starting sync playwright...")
    with sync_playwright() as p:
        print("Connecting to browser...")
        try:
            # Try specific path if root fails, but log said /
            browser = p.chromium.connect("ws://playwright-service:3000/")
            print("Connected!")
            
            page = browser.new_page()
            
            print("Navigating to Dashboard...")
            page.goto("http://yawamf-frontend", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.screenshot(path="frontend_state.png", full_page=True)
            print("Saved frontend_state.png")
            
            print("Navigating to Settings...")
            page.goto("http://yawamf-frontend/settings", timeout=20000, wait_until="domcontentloaded")
            page.wait_for_timeout(2000)
            page.screenshot(path="frontend_settings.png", full_page=True)
            print("Saved frontend_settings.png")
            
            browser.close()
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    main()