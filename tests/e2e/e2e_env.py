import os

BASE_URL = os.environ.get("YAWAMF_BASE_URL", "http://yawamf-frontend")
PLAYWRIGHT_WS = os.environ.get("PLAYWRIGHT_WS", "ws://playwright-service:3000/")
