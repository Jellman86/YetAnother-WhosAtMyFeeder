from playwright.sync_api import sync_playwright
import pytest

from e2e_env import BASE_URL, PLAYWRIGHT_WS


def test_leaderboard_inspect():
    with sync_playwright() as p:
        browser = p.chromium.connect(PLAYWRIGHT_WS)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
            locale="en-US",
        )
        page = context.new_page()
        page.goto(f"{BASE_URL}/species", timeout=30000)
        page.wait_for_load_state("domcontentloaded")

        if page.get_by_text("No species detected yet").is_visible():
            context.close()
            browser.close()
            pytest.skip("No species detected yet")

        # Ensure leaderboard table is visible
        table_wrap = page.get_by_test_id("leaderboard-table-wrap")
        table_wrap.wait_for(state="visible", timeout=15000)

        # Graph card checks
        graph_heading = page.get_by_text("Detections over time")
        graph_heading.wait_for(state="visible", timeout=15000)
        graph_card = graph_heading.locator("xpath=ancestor::div[contains(@class, 'card-base')]").first
        canvas = graph_card.locator(".apexcharts-canvas").first
        canvas.wait_for(state="visible", timeout=15000)

        # Default view is the raw histogram with smoothing disabled.
        raw_button = graph_card.get_by_role("button", name="Raw").first
        histogram_button = graph_card.get_by_role("button", name="Histogram").first
        assert raw_button.get_attribute("aria-pressed") == "true"
        assert histogram_button.get_attribute("aria-pressed") == "true"
        bar_count = graph_card.locator(".apexcharts-bar-series path").count()
        area_count = graph_card.locator(".apexcharts-area-series path").count()
        assert bar_count > 0
        assert area_count == 0

        # Summary stats under the chart should still be present even when
        # sunrise/sunset footer chips are also rendered later in the card.
        card_text = graph_card.inner_text().upper()
        print(f"Graph card text: {card_text[:400]}")
        assert "TOTAL:" in card_text
        assert "PEAK:" in card_text
        assert "AVG:" in card_text

        # Sort buttons and top rows snapshot
        def top_rows_snapshot():
            rows = page.locator("tbody tr")
            names = []
            count = min(rows.count(), 5)
            for i in range(count):
                names.append(rows.nth(i).locator("td").nth(1).inner_text().split("\n")[0].strip())
            return names

        initial_names = top_rows_snapshot()

        for label in ["Total", "Day", "Week", "Month"]:
            page.locator("button.tab-button", has_text=label).first.click()
            page.wait_for_timeout(300)
            names = top_rows_snapshot()
            print(f"Top rows after {label}: {names}")
            if label in ["Week", "Month"]:
                bar_count = graph_card.locator(".apexcharts-bar-series .apexcharts-series path").count()
                print(f"Bar count after {label}: {bar_count}")
                assert bar_count > 0
            else:
                raw_bar_count = graph_card.locator(".apexcharts-bar-series path").count()
                print(f"Bar count after {label}: {raw_bar_count}")
                assert raw_bar_count > 0

        # Screenshot for manual review
        page.screenshot(path="/config/workspace/YA-WAMF/tests/e2e/screenshots/leaderboard-inspect.png", full_page=True)

        context.close()
        browser.close()
