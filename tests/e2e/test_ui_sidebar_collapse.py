import pytest
from playwright.sync_api import sync_playwright
import time

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service at ws://playwright-service:3000/...")
    with sync_playwright() as p:
        try:
            # Connect using the internal Docker network hostname
            browser = p.chromium.connect("ws://playwright-service:3000/")
            print("Connected to Playwright service.")
            yield browser
            browser.close()
        except Exception as e:
            print(f"Failed to connect to Playwright service: {e}")
            raise e

@pytest.fixture(scope="module")
def page(browser):
    context = browser.new_context(
        viewport={"width": 1920, "height": 1080}, # Wide screen to see the "dead space"
        ignore_https_errors=True
    )
    page = context.new_page()
    yield page
    context.close()

def test_sidebar_collapse_layout(page):
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Settings: {base_url}/settings")
    page.goto(f"{base_url}/settings", timeout=30000)
    page.wait_for_load_state("domcontentloaded")
    
    # 1. Switch to Vertical Layout
    print("Switching to Vertical Layout...")
    
    # Click Appearance tab
    try:
        page.get_by_role("button", name="Appearance").click()
    except:
        page.get_by_text("Appearance").click()
        
    # Wait for tab content
    page.wait_for_selector("text=Navigation Layout", timeout=5000)
    
    # Click "Vertical" button
    # The button contains text "Vertical" and icon "⇕"
    # We can find it by text "Vertical" inside a button
    page.locator("button").filter(has_text="Vertical").click()
    
    # Wait for layout change (sidebar should appear)
    # Sidebar has a specific class or ID? 
    # In Sidebar.svelte: <aside class="fixed left-0 top-0 ...">
    page.wait_for_selector("aside", timeout=5000)
    print("Vertical sidebar visible.")
    
    # Take screenshot of vertical layout expanded
    page.screenshot(path="layout_vertical_expanded.png")
    
    # 2. Collapse Sidebar
    print("Collapsing sidebar...")
    # The button has title="Collapse sidebar"
    collapse_btn = page.get_by_title("Collapse sidebar")
    collapse_btn.click()
    
    # Wait for transition (Sidebar.svelte has transition-all duration-300)
    time.sleep(1) 
    
    # Take screenshot of collapsed layout
    page.screenshot(path="layout_vertical_collapsed.png")
    
    # 3. Analyze Main Content Margin
    # App.svelte: <main class="... {currentLayout === 'vertical' ? (isSidebarCollapsed ? 'md:ml-20' : 'md:ml-64') : ''}">
    # We expect ml-20 (80px)
    
    main_margin_left = page.locator("main").evaluate("el => getComputedStyle(el).marginLeft")
    print(f"Main content margin-left: {main_margin_left}")
    
    # Check if it matches 80px (approx)
    if "80px" in main_margin_left:
        print("Margin updated correctly to 80px.")
    else:
        print(f"WARNING: Margin might be incorrect. Expected 80px, got {main_margin_left}")

    # 4. Check for 'dead space'
    # We can check the width of the main content container
    main_width = page.locator("main").evaluate("el => el.getBoundingClientRect().width")
    window_width = page.evaluate("window.innerWidth")
    
    print(f"Window width: {window_width}")
    print(f"Main content width: {main_width}")
    
    # If main width + margin is significantly less than window width, we have dead space.
    # The container has max-w-7xl (approx 1280px).
    # On a 1920px screen:
    # 80px (margin) + 1280px (max-w) = 1360px.
    # Remaining: 1920 - 1360 = 560px.
    # Since it's mx-auto, this 560px should be split between left and right (inside the margin offset? No, mx-auto centers within the parent flex-1).
    
    # Let's verify the "dead space" claim by screenshot visualization
    # and maybe checking if the content is centered within the available space (1920-80).
    
    print("\n[SUCCESS] Sidebar Collapse Test Completed.")
