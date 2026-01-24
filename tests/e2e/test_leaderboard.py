from playwright.sync_api import sync_playwright


def test_leaderboard_layout():
    with sync_playwright() as p:
        browser = p.chromium.connect("ws://playwright-service:3000/")
        context = browser.new_context(
            viewport={"width": 360, "height": 800},
            ignore_https_errors=True,
            locale="en-US",
        )
        page = context.new_page()
        page.goto("http://yawamf-frontend/species", timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        if page.get_by_text("No species detected yet").is_visible():
            context.close()
            browser.close()
            return

        table_wrap = page.get_by_test_id("leaderboard-table-wrap")
        table_wrap.wait_for(state="visible", timeout=15000)
        scroll_width = table_wrap.evaluate("el => el.scrollWidth")
        client_width = table_wrap.evaluate("el => el.clientWidth")
        assert scroll_width >= client_width

        context.close()
        browser.close()
