import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect("ws://playwright-service:3000/")
        except Exception as e:
            print(f"Failed to connect to playwright-service: {e}")
            return

        page = await browser.new_page()
        
        # Capture console logs and filter out the flood to see the start
        logs = []
        page.on("console", lambda msg: logs.append(f"CONSOLE {msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: logs.append(f"PAGE ERROR: {exc}"))

        url = "http://yawamf-monalithic:8080"
        print(f"Navigating to {url}...")
        
        try:
            # Navigate and wait for a very short time before the loop explodes
            await page.goto(url, wait_until="commit")
            await asyncio.sleep(2) 
            
            print(f"Captured {len(logs)} log entries in first 2 seconds.")
            # Print unique logs or just the first few
            seen_logs = set()
            for log in logs:
                if "effect_update_depth_exceeded" not in log:
                    print(log)
                elif "effect_update_depth_exceeded" not in seen_logs:
                    print(log)
                    seen_logs.add("effect_update_depth_exceeded")
            
            # Try to get window location
            location = await page.evaluate("window.location.pathname")
            print(f"Window location pathname: {location}")
            
        except Exception as e:
            print(f"Diagnostic failed: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
