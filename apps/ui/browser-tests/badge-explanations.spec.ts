import { test, expect, type Page } from '@playwright/test';

async function open(page: Page) {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => new URL(route.request().url()).pathname.endsWith('.jpg')
        ? route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="#0f766e"/></svg>' })
        : route.fulfill({ json: {} }));
    await page.goto('/browser-tests/thumbnail-refresh.html?badges=1');
}

test('card status explanations are reachable above the record action and dismiss with Escape', async ({ page, isMobile }) => {
    test.skip(isMobile, 'Hover requires a hovering pointer; touch is tested separately.');
    await open(page);
    const card = page.locator('[data-surface="card-A"]');
    for (const [label, text] of [
        ['Favorite', 'Favorite'],
        ['Verified', 'A matching bird call was heard near this capture.'],
        ['Missing upstream', 'Frigate no longer has this event or media']
    ]) {
        await card.locator(`[aria-label="${label}"]`).hover({ timeout: 2000 });
        await expect(page.getByRole('tooltip')).toHaveText(text, { timeout: 2000 });
        await page.keyboard.press('Escape');
        await expect(page.getByRole('tooltip')).toHaveCount(0);
    }
    await expect(page.locator('output[aria-label="Opened records"]')).toHaveText('0');
});

test('confidence and full-visit badges explain themselves on keyboard focus without playing', async ({ page }) => {
    await open(page);
    const card = page.locator('[data-surface="card-A"]');
    await card.getByRole('button', { name: 'Identification confidence: 80%.' }).focus();
    await expect(page.getByRole('tooltip')).toHaveText('Identification confidence: 80%.', { timeout: 2000 });
    await page.keyboard.press('Escape');
    await card.locator('[aria-label="Full visit clip ready"]').focus();
    expect(await card.locator('[aria-label="Full visit clip ready"]').evaluate(node => getComputedStyle(node).position)).toBe('absolute');
    await expect(page.getByRole('tooltip')).toHaveText('Full visit clip ready', { timeout: 2000 });
    await page.keyboard.press('Enter');
    await expect(page.locator('output[aria-label="Played clips"]')).toHaveText('0');
    const box = await page.getByRole('tooltip').boundingBox();
    expect(box).not.toBeNull();
    expect(box!.x).toBeGreaterThanOrEqual(0);
    expect(box!.x + box!.width).toBeLessThanOrEqual(page.viewportSize()!.width);
});

test('a pinned explanation closes when its badge scrolls out of the viewport', async ({ page }) => {
    await open(page);
    await page.locator('[data-surface="card-A"]').getByRole('button', { name: 'Identification confidence: 80%.' }).click();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect(page.getByRole('tooltip')).toHaveCount(0, { timeout: 2000 });
});

test('capture badge explanations escape clipping and close with their scrolling panel', async ({ page }) => {
    await open(page);
    await page.route('**/api/visits/*/captures*', route => route.fulfill({ json: {
        total: 21,
        captures: Array.from({ length: 20 }, (_, index) => ({
            frigate_event: `capture-${index}`, display_name: 'Eurasian Blackbird', scientific_name: 'Turdus merula',
            common_name: 'Eurasian Blackbird', camera_name: 'birdcam', detection_time: '2026-10-02T10:42:21Z', score: 0.95
        }))
    } }));
    await page.goto('/browser-tests/visits.html?floating=1');
    await page.locator('[data-fixture-visit] [data-visit-captures-toggle]').click();
    const panel = page.locator('[data-fixture-visit] [data-visit-captures-floating]');
    const badge = panel.getByRole('button', { name: 'Identification confidence: 95%.' }).nth(2);
    await badge.click();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await expect(panel).toBeVisible();
    await badge.click();
    const target = await badge.evaluate(node => {
        const parent = node.closest('[popover]')!;
        return node.getBoundingClientRect().top - parent.getBoundingClientRect().top + node.getBoundingClientRect().height + 16;
    });
    await panel.evaluate((node, top) => { node.scrollTop = top; }, target);
    await expect(page.getByRole('tooltip')).toHaveCount(0, { timeout: 2000 });
    await panel.evaluate(node => { node.scrollTop = 0; });
    await badge.click();
    await expect(page.getByRole('tooltip')).toBeVisible();
    await panel.evaluate(node => (node as HTMLElement).hidePopover());
    await expect(page.getByRole('tooltip')).toHaveCount(0, { timeout: 2000 });
});

test('touch opens a badge explanation and an outside tap opens the record normally', async ({ page, isMobile }) => {
    test.skip(!isMobile, 'Touch device case.');
    await open(page);
    const badge = page.locator('[data-surface="card-A"] [aria-label="Missing upstream"]');
    await badge.tap({ timeout: 2000 });
    await expect(page.getByRole('tooltip')).toHaveText('Frigate no longer has this event or media', { timeout: 2000 });
    await expect(page.locator('output[aria-label="Opened records"]')).toHaveText('0');
    await page.locator('[data-surface="card-A"] [data-detection-card] > div > button').first().tap({ position: { x: 280, y: 120 } });
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await expect(page.locator('output[aria-label="Opened records"]')).toHaveText('1');
});
