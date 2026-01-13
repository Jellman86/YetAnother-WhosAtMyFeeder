import pytest
from playwright.sync_api import sync_playwright, expect

@pytest.fixture(scope="module")
def browser():
    print("\nConnecting to Playwright service...")
    with sync_playwright() as p:
        try:
            # Connect to the remote browser in the Playwright container
            browser = p.chromium.connect("ws://playwright-service:3000/")
            print("Connected to Playwright service.")
            yield browser
            browser.close()
        except Exception as e:
            print(f"Failed to connect to Playwright: {e}")
            raise e

@pytest.fixture(scope="module")
def page(browser):
    context = browser.new_context(
        viewport={"width": 1280, "height": 720},
        ignore_https_errors=True
    )
    # Set English as default locale
    context.set_extra_http_headers({"Accept-Language": "en"})
    
    page = context.new_page()
    
    # Capture console logs
    page.on("console", lambda msg: print(f"BROWSER_CONSOLE: {msg.type}: {msg.text}"))
    page.on("pageerror", lambda err: print(f"BROWSER_ERROR: {err}"))
    
    yield page
    context.close()

def test_i18n_and_accessibility(page):
    # Use container name as hostname since they are on the same network
    base_url = "http://yawamf-frontend"
    
    print(f"\n[1] Navigating to Dashboard: {base_url}")
    try:
        page.goto(base_url, timeout=30000)
        # Avoid networkidle due to SSE
        page.wait_for_load_state("domcontentloaded")
    except Exception as e:
        print(f"Navigation failed: {e}")
        raise e

    # --- 1. Test Language Switching (Spanish) ---
    print("\n[2] Testing Language Switch (ES)...")
    
    # Open Language Dropdown in Header
    # It has aria-label="Language" (translated) or the globe icon
    # Initially in English, label is "Language"
    # The button has the current language name "English" text
    
    # Click the language selector button (it shows "English")
    page.get_by_role("button", name="Language").click()
    
    # Click "Español" in the dropdown
    # The dropdown role is "menu" and items are "menuitem"
    page.get_by_role("menuitem", name="Español").click()
    
    # Verify Dashboard text changes
    # "Dashboard" -> "Tablero"
    # "Live Feed" -> "Transmisión en vivo"
    # "Discovery Feed" -> "Feed de Descubrimiento"
    
    # Allow small time for reactivity
    page.wait_for_timeout(500) 
    
    # Check for "Tablero" in navigation
    expect(page.get_by_role("button", name="Tablero")).to_be_visible()
    
    # Check for "Transmisión en vivo" header
    expect(page.get_by_text("Transmisión en vivo")).to_be_visible()
    
    print("✅ Language switched to Spanish successfully")

    # --- 2. Test Accessibility Settings ---
    print("\n[3] Testing Accessibility Settings...")
    
    # Navigate to Settings
    # "Settings" in Spanish is "Ajustes"
    page.get_by_role("button", name="Ajustes").click()
    page.wait_for_url("**/settings")
    
    # Switch to Accessibility Tab
    # "Accessibility" in Spanish is "Accesibilidad"
    page.get_by_text("Accesibilidad", exact=True).click()
    
    # 2.1 High Contrast
    print("Testing High Contrast Toggle...")
    # Find the toggle for "Alto contraste" (High Contrast)
    # It's a button next to the label
    # We can find the button relative to the text
    high_contrast_btn = page.locator("div").filter(has_text="Alto contraste").last.get_by_role("button")
    high_contrast_btn.click()
    
    # Verify class on html element
    expect(page.locator("html")).to_have_class(pytest.helpers.re.compile(r"high-contrast"))
    print("✅ High Contrast class applied")
    
    # Turn off High Contrast
    high_contrast_btn.click()
    expect(page.locator("html")).not_to_have_class(pytest.helpers.re.compile(r"high-contrast"))

    # 2.2 Dyslexia Font
    print("Testing Dyslexia Font Toggle...")
    # "Fuente para dislexia"
    dyslexia_btn = page.locator("div").filter(has_text="Fuente para dislexia").last.get_by_role("button")
    dyslexia_btn.click()
    
    # Verify class on body element
    expect(page.locator("body")).to_have_class(pytest.helpers.re.compile(r"font-dyslexic"))
    print("✅ Dyslexia Font class applied")
    
    # Turn off
    dyslexia_btn.click()
    expect(page.locator("body")).not_to_have_class(pytest.helpers.re.compile(r"font-dyslexic"))

    # 2.3 Reduced Motion
    print("Testing Reduced Motion Toggle...")
    # "Movimiento reducido"
    motion_btn = page.locator("div").filter(has_text="Movimiento reducido").last.get_by_role("button")
    motion_btn.click()
    
    # Verify class on body
    expect(page.locator("body")).to_have_class(pytest.helpers.re.compile(r"motion-reduce"))
    print("✅ Reduced Motion class applied")

    # --- 3. Restore English ---
    print("\n[4] Restoring Language to English...")
    # Header language selector now says "Español"
    page.get_by_role("button", name="Idioma").first.click() # "Language" in Spanish is "Idioma"
    page.get_by_role("menuitem", name="English").click()
    
    # Verify return to "Settings" (English)
    expect(page.get_by_role("heading", name="Settings")).to_be_visible()
    
    print("\n[SUCCESS] i18n and Accessibility Test Completed.")

# Helper for regex matching
def pytest_configure():
    pytest.helpers = type('Helpers', (), {})
    import re
    pytest.helpers.re = re
