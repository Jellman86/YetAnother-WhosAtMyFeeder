import os
import time
from playwright.sync_api import sync_playwright

def capture_ui_review():
    ws_url = os.environ.get("PLAYWRIGHT_WS", "ws://playwright-service:3000/")
    base_url = "http://yawamf-frontend"
    output_dir = "/config/workspace/playwright-results/review"
    
    print(f"Connecting to {ws_url}...")
    with sync_playwright() as p:
        browser = p.chromium.connect(ws_url)
        
        # 1. Desktop Light Mode
        print("Capturing Desktop Light Mode...")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("document.documentElement.classList.remove('dark'); localStorage.setItem('theme', 'light');")
        time.sleep(2) 
        page.screenshot(path=f"{output_dir}/desktop_light_dashboard.png", full_page=True)
        
        page.click("text=Leaderboard")
        page.wait_for_url("**/species")
        time.sleep(1)
        page.screenshot(path=f"{output_dir}/desktop_light_leaderboard.png", full_page=True)
        context.close()

        # 2. Desktop Dark Mode
        print("Capturing Desktop Dark Mode...")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark');")
        time.sleep(2)
        page.screenshot(path=f"{output_dir}/desktop_dark_dashboard.png", full_page=True)
        
        page.click("text=Leaderboard")
        page.wait_for_url("**/species")
        time.sleep(1)
        page.screenshot(path=f"{output_dir}/desktop_dark_leaderboard.png", full_page=True)
        
        # 3. Video Player (in Dark Mode)
        print("Capturing Video Player...")
        page.goto(f"{base_url}/events") # More reliable to have detections here
        page.wait_for_load_state("domcontentloaded")
        try:
            # Find a card that has a clip (we can't easily know, so we try the first few)
            cards = page.locator(".group.relative")
            found = False
            for i in range(min(cards.count(), 5)):
                card = cards.nth(i)
                card.hover()
                play_btn = card.locator("button[aria-label*='play'], button[aria-label*='Play']")
                if play_btn.count() > 0:
                    play_btn.first.click(force=True)
                    time.sleep(5) # Wait for player
                    page.screenshot(path=f"{output_dir}/video_player_modal.png")
                    found = True
                    break
            if not found:
                print("No play button found on any of the first 5 cards.")
        except Exception as e:
            print(f"Could not capture video player: {e}")
        
        context.close()

        # 4. Mobile View (Dark Mode)
        print("Capturing Mobile View...")
        context = browser.new_context(
            viewport={"width": 375, "height": 812},
            is_mobile=True,
            user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 13_2_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/13.0.3 Mobile/15E148 Safari/604.1"
        )
        page = context.new_page()
        page.goto(base_url)
        page.wait_for_load_state("domcontentloaded")
        page.evaluate("document.documentElement.classList.add('dark'); localStorage.setItem('theme', 'dark');")
        time.sleep(2)
        page.screenshot(path=f"{output_dir}/mobile_dark_dashboard.png")
        
        # Open mobile menu
        try:
            # The mobile menu button is usually the last one in the header
            menu_btn = page.locator("header button").last
            menu_btn.click(force=True)
            time.sleep(1)
            page.screenshot(path=f"{output_dir}/mobile_menu_open.png")
            
            # Click Leaderboard in the mobile menu
            page.locator("nav button >> text=Leaderboard").first.click(force=True)
            page.wait_for_url("**/species")
            time.sleep(1)
            page.screenshot(path=f"{output_dir}/mobile_dark_leaderboard.png")
        except Exception as e:
            print(f"Mobile navigation failed: {e}")
            
        context.close()
        browser.close()
        print(f"Done. Screenshots saved to {output_dir}")

if __name__ == "__main__":
    capture_ui_review()
