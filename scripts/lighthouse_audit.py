import asyncio
import json
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        try:
            browser = await p.chromium.connect("ws://playwright-service:3000/")
        except Exception as e:
            print(f"Failed to connect to playwright-service: {e}")
            return

        page = await browser.new_page()
        
        # We can't run full Lighthouse inside playwright-service easily without the CLI,
        # but we can simulate some checks and capture the performance timeline.
        
        url = "http://yawamf-monalithic:8080"
        print(f"Navigating to {url} for performance audit...")
        
        # Start tracing
        await browser.start_tracing(page=page, path="/config/workspace/YA-WAMF/playwright-results/trace.json")
        
        try:
            # We know it might fail with infinite loop, so we set a timeout
            await page.goto(url, wait_until="commit", timeout=10000)
            await asyncio.sleep(5)
        except Exception as e:
            print(f"Navigation timed out or failed (as expected): {e}")
        
        await browser.stop_tracing()
        print("Trace saved to playwright-results/trace.json")
        
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
