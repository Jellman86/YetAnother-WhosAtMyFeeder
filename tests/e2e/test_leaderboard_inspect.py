from playwright.sync_api import sync_playwright
import os
import pytest


def test_leaderboard_inspect():
    with sync_playwright() as p:
        ws_endpoint = os.getenv("PLAYWRIGHT_WS", "ws://playwright-service:3000/")
        browser = p.chromium.connect(ws_endpoint)
        context = browser.new_context(
            viewport={"width": 1280, "height": 900},
            ignore_https_errors=True,
            locale="en-US",
        )
        page = context.new_page()
        page.goto("http://yawamf-frontend/species", timeout=30000)
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
        svg = graph_card.locator("svg").first
        svg.wait_for(state="visible", timeout=15000)

        axis_labels = svg.locator("text").all_inner_texts()
        assert "Detections" in axis_labels
        assert "Days" in axis_labels

        # Capture line path for comparison
        line_path = svg.locator("path[stroke]").get_attribute("d")
        assert line_path

        # Summary stats under the chart
        summary_text = graph_card.locator("text=/30-day total:/").inner_text()
        assert "Peak day:" in summary_text
        assert "Avg/day:" in summary_text

        # Sort buttons and top rows snapshot
        def top_rows_snapshot():
            rows = page.locator("tbody tr")
            names = []
            count = min(rows.count(), 5)
            for i in range(count):
                names.append(rows.nth(i).locator("td").nth(1).inner_text().split("\n")[0].strip())
            return names

        initial_names = top_rows_snapshot()

        for label in ["Day", "Week", "Month"]:
            page.get_by_role("button", name=label).click()
            page.wait_for_timeout(300)
            names = top_rows_snapshot()
            print(f"Top rows after {label}: {names}")

        # Graph should not change with sort buttons (sort only affects table)
        line_path_after = svg.locator("path[stroke]").get_attribute("d")
        print(f"Graph path changed: {line_path != line_path_after}")

        # Screenshot for manual review
        page.screenshot(path="/config/workspace/YA-WAMF/tests/e2e/screenshots/leaderboard-inspect.png", full_page=True)

        context.close()
        browser.close()
