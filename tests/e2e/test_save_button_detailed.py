#!/usr/bin/env python3
"""
Detailed test to diagnose why the save button isn't appearing
"""
from playwright.sync_api import sync_playwright
import time

def run():
    console_logs = []
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(viewport={"width": 1920, "height": 1080})
        page = context.new_page()

        # Capture all console messages
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: errors.append(str(err)))

        print("=" * 80)
        print("DETAILED SAVE BUTTON DIAGNOSTIC TEST")
        print("=" * 80)

        print("\n[1] Navigating to Settings...")
        page.goto("http://yawamf-frontend/settings", wait_until="domcontentloaded", timeout=30000)
        time.sleep(3)  # Give console logs time to appear

        print("\n[2] Console logs on page load:")
        for log in console_logs:
            if "isDirty" in log or "Calculating" in log or "Dirty Setting" in log:
                print(f"  {log}")

        print("\n[3] Checking initial button state...")
        save_button = page.locator('button:has-text("Apply Settings")')
        button_count = save_button.count()
        print(f"  Save button count: {button_count}")
        if button_count > 0:
            is_visible = save_button.is_visible()
            print(f"  Button visible: {is_visible}")
        else:
            print("  Button not in DOM (expected if no changes)")

        print("\n[4] Looking for classification threshold slider...")
        # Try multiple selectors
        threshold_input = page.locator('input[type="range"]').first
        if threshold_input.count() == 0:
            threshold_input = page.locator('input[type="number"]').first

        if threshold_input.count() > 0:
            print("  Found input element")
            current_value = threshold_input.input_value()
            print(f"  Current value: {current_value}")

            print("\n[5] Changing value to trigger isDirty...")
            # Clear console logs
            console_logs.clear()

            # Change the value
            new_value = "0.65" if current_value != "0.65" else "0.75"
            threshold_input.fill(new_value)
            threshold_input.blur()  # Trigger change event

            time.sleep(1)  # Wait for reactive updates

            print("\n[6] Console logs after change:")
            for log in console_logs:
                if "isDirty" in log or "Dirty Setting" in log or "Calculating" in log:
                    print(f"  {log}")

            print("\n[7] Checking button state after change...")
            button_count_after = save_button.count()
            print(f"  Save button count: {button_count_after}")

            if button_count_after > 0:
                is_visible_after = save_button.is_visible()
                print(f"  Button visible: {is_visible_after}")

                # Take screenshot
                page.screenshot(path="/config/workspace/save_button_visible.png", full_page=True)
                print("  Screenshot saved: /config/workspace/save_button_visible.png")
            else:
                print("  ❌ Button STILL NOT IN DOM - This is the bug!")

                # Take screenshot for debugging
                page.screenshot(path="/config/workspace/save_button_missing.png", full_page=True)
                print("  Screenshot saved: /config/workspace/save_button_missing.png")

                # Check if isDirty is being calculated
                print("\n[8] Inspecting isDirty state via JS...")
                try:
                    # Try to access page state
                    html = page.content()
                    if "Apply Settings" in html:
                        print("  Button HTML exists but might be hidden by CSS")
                    else:
                        print("  Button HTML not in page at all")
                except Exception as e:
                    print(f"  Error checking HTML: {e}")
        else:
            print("  ❌ Could not find any input elements to modify!")
            page.screenshot(path="/config/workspace/settings_no_inputs.png", full_page=True)

        print("\n[9] All console logs:")
        for log in console_logs:
            print(f"  {log}")

        if errors:
            print("\n[10] JavaScript Errors:")
            for error in errors:
                print(f"  ❌ {error}")

        print("\n" + "=" * 80)
        print("TEST COMPLETE")
        print("=" * 80)

        browser.close()

if __name__ == "__main__":
    run()
