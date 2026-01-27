#!/usr/bin/env bash
set -euo pipefail

URL="${1:-https://yetanotherwhosatmyfeeder.pownet.uk/}"
OUT_DIR="/config/workspace/playwright-results/lighthouse-public"
LH_JSON="$OUT_DIR/lighthouse-public.json"
CONSOLE_JSON="$OUT_DIR/console-errors.json"

mkdir -p "$OUT_DIR"

# Run Lighthouse inside the Playwright container (Chromium is available there)
docker exec playwright-service sh -c "CHROME_PATH=/ms-playwright/chromium-1200/chrome-linux64/chrome \
  npx -y lighthouse \"$URL\" \
  --chrome-flags=\"--headless --no-sandbox --disable-gpu\" \
  --output=json --output-path=/tmp/lighthouse-public.json"

# Copy the report to the workspace
docker cp playwright-service:/tmp/lighthouse-public.json "$LH_JSON"

# Capture console errors via Playwright (requires playwright python package)
PYTHON_BIN="/config/workspace/YA-WAMF/backend/venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python3"
fi
"$PYTHON_BIN" /config/workspace/YA-WAMF/tests/e2e/capture_console_errors.py \
  --url "$URL" \
  --output "$CONSOLE_JSON"

printf "\nSaved Lighthouse report: %s\n" "$LH_JSON"
printf "Saved console logs: %s\n" "$CONSOLE_JSON"
