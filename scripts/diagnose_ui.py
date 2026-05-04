
import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        # Connect to the remote browser container
        # Note: Using 'playwright-service' if DNS works, else would need IP. 
        # The guide says ws://playwright-service:3000/
        try:
            browser = await p.chromium.connect("ws://playwright-service:3000/")
        except Exception as e:
            print(f"Failed to connect to playwright-service: {e}")
            return

        page = await browser.new_page()
        
        # Capture console logs
        page.on("console", lambda msg: print(f"CONSOLE {msg.type}: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"PAGE ERROR: {exc}"))

        # Navigate using the internal container name or IP
        # The guide says http://yawamf-frontend, but we have yawamf-monalithic
        url = "http://yawamf-monalithic:8080"
        print(f"Navigating to {url}...")
        
        try:
            await page.goto(url, wait_until="domcontentloaded")
            await asyncio.sleep(5)  # Wait a bit for Svelte to fail/load
            
            await page.screenshot(path="/config/workspace/YA-WAMF/playwright-results/failure_audit.png")
            print("Screenshot saved to playwright-results/failure_audit.png")
            
            # Check for common Svelte 5 error markers or empty root
            content = await page.content()
            if "svelte" in content.lower():
                print("Found 'svelte' in page content.")
            else:
                print("Warning: 'svelte' not found in page content. UI might not be mounting.")
                
        except Exception as e:
            print(f"Navigation failed: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
