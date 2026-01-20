# 🎭 Playwright UI Testing Guide (Container-to-Container)

This guide details how to perform full UI testing of YA-WAMF using the external `playwright-service` container. This approach avoids installing heavy browser dependencies in the development environment and ensures tests run against the actual running containers.

---

## 🏗️ Architecture

1.  **`code-server-sjp`**: The development environment where you run the test scripts.
2.  **`playwright-service`**: A dedicated container (`mcr.microsoft.com/playwright`) running a Playwright server on port 3000.
3.  **`yawamf-frontend`**: The Svelte 5 application being tested.
4.  **Network**: All containers must be on the same Docker network (e.g., `general_brg`).

---

## 🚀 Step-by-Step Execution

### 1. Verify Connectivity
From the terminal, ensure you can reach the Playwright service:
```bash
# Check if the service is reachable by hostname
ping -c 1 playwright-service
```

**Note for sandboxed environments:** `ping` may be blocked, and `playwright-service` DNS may not resolve. If that happens, use the container IP from Docker:
```bash
docker inspect -f '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}' playwright-service
```
Then connect Playwright to `ws://<container-ip>:3000/`. You can also set `PLAYWRIGHT_WS` to override the default:
```bash
export PLAYWRIGHT_WS=ws://<container-ip>:3000/
```

### 2. Environment Setup
The testing script requires `playwright` and `pytest` Python packages. You can use the existing backend virtual environment:

```bash
source backend/venv/bin/activate
# If not already installed:
pip install pytest playwright
```

### 3. The Test Script Pattern
To connect to the external container, your script must use `p.chromium.connect("ws://playwright-service:3000/")`.

**Crucial Note on URLs:**
- Use `http://yawamf-frontend` as the base URL, **NOT** `localhost`. Since Playwright is running *inside* its own container, it resolves `yawamf-frontend` via Docker DNS.

**If DNS is unavailable:** use the IP from `docker inspect` with `ws://<container-ip>:3000/` for the Playwright WebSocket, but keep `http://yawamf-frontend` for page navigation.

#### Example Skeleton (`test_ui.py`):
```python
import pytest
from playwright.sync_api import sync_playwright

@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as p:
        # Connect to the remote browser container
        browser = p.chromium.connect("ws://playwright-service:3000/")
        yield browser
        browser.close()

def test_dashboard(browser):
    page = browser.new_page()
    # Navigate using the internal container name
    page.goto("http://yawamf-frontend")
    
    # IMPORTANT: Avoid wait_for_load_state("networkidle") 
    # if your app uses SSE (/api/sse), as it will never finish.
    page.wait_for_load_state("domcontentloaded")
    
    assert "WhosAtMyFeeder" in page.title()
    page.screenshot(path="dashboard.png")
```

### 4. Running the Tests
Execute the tests using `pytest`:

```bash
cd tests/e2e
python3 -m pytest test_ui_full_container.py -s
```

---

## 🛠️ Common Pitfalls & Solutions

### ❌ `ECONNREFUSED`
- **Cause**: Trying to connect to `localhost:3000` or `127.0.0.1:3000`.
- **Fix**: Use `ws://playwright-service:3000/`.

### ❌ Timeout waiting for `networkidle`
- **Cause**: The SSE connection (`/api/sse`) keeps the network active indefinitely.
- **Fix**: Use `page.wait_for_load_state("domcontentloaded")` or wait for a specific element with `page.wait_for_selector()`.

### ❌ Screenshot Permissions
- **Issue**: Screenshots might be saved in locations the user can't access.
- **Fix**: Check the `volumes` mapping in `docker-compose.yml`. In this environment, results are shared at `/config/workspace/playwright-results`.

---

## 🖼️ Viewing Results
Screenshots taken during the test are saved in the current directory (or the path specified in `page.screenshot()`). Use the file explorer to view the generated images for visual confirmation.

- `dashboard_load.png`
- `explorer_page.png`
- `leaderboard_page.png`
- `settings_page.png`

---

## 🤖 Guide for AI Agents
When instructing an AI to run UI tests in this environment:
1.  **Tell it to use the `playwright-service` container**.
2.  **Specify the WebSocket URL**: `ws://playwright-service:3000/`.
3.  **Specify the Target URL**: `http://yawamf-frontend/`.
4.  **Remind it about SSE**: Warn the agent not to wait for `networkidle`.

*Updated: 11 January 2026*
