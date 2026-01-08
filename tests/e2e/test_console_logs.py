#!/usr/bin/env python3
"""
Test specifically to capture console logs and check if isDirty is running
"""
from playwright.sync_api import sync_playwright
import time

def run():
    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Store ALL console messages
        all_console = []
        def handle_console(msg):
            text = msg.text
            log_type = msg.type
            all_console.append(f"[{log_type.upper()}] {text}")
            print(f"CONSOLE [{log_type}]: {text}")

        page.on("console", handle_console)
        page.on("pageerror", lambda err: print(f"❌ PAGE ERROR: {err}"))

        print("\n" + "=" * 80)
        print("CONSOLE LOG CAPTURE TEST")
        print("=" * 80)

        print("\n[1] Navigating to settings...")
        page.goto("http://yawamf-frontend/settings")
        page.wait_for_load_state("domcontentloaded")

        print("\n[2] Waiting for page to fully load...")
        time.sleep(5)  # Wait longer to capture logs

        print(f"\n[3] Total console messages captured: {len(all_console)}")

        # Check if settingsStore loaded
        settings_loaded = page.evaluate("""
            () => {
                // Try to check if settings are loaded
                return {
                    settingsElementExists: !!document.querySelector('h2'),
                    bodyText: document.body.innerText.substring(0, 200)
                };
            }
        """)
        print(f"\n[4] Page state check:")
        print(f"  Settings element exists: {settings_loaded['settingsElementExists']}")
        print(f"  Body text preview: {settings_loaded['bodyText'][:100]}")

        print("\n[5] Looking for isDirty-related console logs:")
        found_isdirty = False
        for log in all_console:
            if "isDirty" in log.lower() or "calculating" in log.lower() or "dirty" in log.lower():
                print(f"  {log}")
                found_isdirty = True

        if not found_isdirty:
            print("  ❌ NO isDirty logs found!")
            print("\n[6] Showing ALL console logs:")
            for log in all_console:
                print(f"  {log}")

        # Try to manually trigger isDirty by evaluating JS
        print("\n[7] Attempting to check isDirty via JavaScript...")
        try:
            result = page.evaluate("""
                () => {
                    // Try to find if button is in DOM but hidden
                    const buttons = Array.from(document.querySelectorAll('button'));
                    const applyButton = buttons.find(b => b.textContent.includes('Apply Settings'));

                    return {
                        totalButtons: buttons.length,
                        hasApplyButton: !!applyButton,
                        applyButtonVisible: applyButton ? window.getComputedStyle(applyButton).display !== 'none' : false,
                        buttonTexts: buttons.slice(0, 10).map(b => b.textContent.trim().substring(0, 30))
                    };
                }
            """)
            print(f"  Total buttons: {result['totalButtons']}")
            print(f"  Has Apply button: {result['hasApplyButton']}")
            if result['hasApplyButton']:
                print(f"  Apply button visible: {result['applyButtonVisible']}")
            print(f"  First 10 button texts: {result['buttonTexts']}")
        except Exception as e:
            print(f"  Error: {e}")

        page.screenshot(path="/config/workspace/console_test.png", full_page=True)
        print("\nScreenshot saved: /config/workspace/console_test.png")

        print("\n" + "=" * 80)
        browser.close()

if __name__ == "__main__":
    run()
