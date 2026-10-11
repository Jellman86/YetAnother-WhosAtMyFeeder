import { test, expect, type Locator, type Page } from '@playwright/test';

// Set EXPLORER_SHOTS to a directory to keep review screenshots outside the test output.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.EXPLORER_SHOTS;

function record(id: string, at: string) {
    return {
        frigate_event: id, display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock',
        camera_name: 'birdcam', detection_time: at, score: 0.91, has_clip: true, temperature: 13.5, weather_condition: 'Clear sky'
    };
}

async function openExplorer(page: Page, query = '') {
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    const visitAt = new Date(Date.now() - 60 * 60 * 1000).toISOString();
    const singleAt = new Date(Date.now() - 2 * 60 * 60 * 1000).toISOString();
    const visit = (id: string, at: string, count: number) => ({
        visit_id: id, start_time: at, end_time: at, capture_count: count, best_score: 0.91, needs_review: false,
        audio_confirmed: false, representative: record(id, at), latest: record(id, at), peak_capture: null
    });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/events') return route.fulfill({ json: [record('first', visitAt), record('single', singleAt)] });
        if (path === '/api/visits') return route.fulfill({ json: { total: 2, gap_seconds: 60, visits: [visit('first', visitAt, 3), visit('single', singleAt, 1)] } });
        if (path === '/api/visits/first/captures') {
            return route.fulfill({ json: { total: 3, captures: [0, 1, 2].map(index => ({ ...record(index ? `first-${index}` : 'first', visitAt), score: 0.8 + index / 20 })) } });
        }
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 4, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        if (path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${query}`);
    await expect(page.locator('[data-explorer-visit="first"] [data-detection-card]')).toBeVisible();
    return errors;
}

function radii(element: Locator) {
    return element.evaluate(node => {
        const style = getComputedStyle(node);
        return [style.borderTopLeftRadius, style.borderTopRightRadius, style.borderBottomRightRadius, style.borderBottomLeftRadius]
            .map(value => Number.parseFloat(value));
    });
}

/** The whole Explorer item, card and captures together, has exactly one outline. */
async function expectOneOutline(item: Locator) {
    const frame = item.locator('[data-detection-card]');
    // The wrapper draws nothing of its own; the card's frame is the only outline.
    expect(await item.evaluate(node => getComputedStyle(node).borderTopWidth)).toBe('0px');
    expect(await item.evaluate(node => getComputedStyle(node).boxShadow)).toBe('none');
    for (const radius of await radii(frame)) expect(radius).toBeGreaterThan(8);
    // Measure both edges together and wait for the card's entrance animation to settle.
    await expect.poll(() => item.evaluate(node => {
        const frame = node.querySelector('[data-detection-card]');
        if (!frame) return Infinity;
        return Math.abs(node.getBoundingClientRect().bottom - frame.getBoundingClientRect().bottom);
    })).toBeLessThanOrEqual(1);
    return frame;
}

for (const theme of ['light', 'dark']) {
    test(`an Explorer card and its captures share one outline (${theme})`, async ({ page }) => {
        const errors = await openExplorer(page, `&theme=${theme}`);
        const item = page.locator('[data-explorer-visit="first"]');
        const frame = await expectOneOutline(item);
        // The captures bar is inside the card's own frame, not a second box beneath it.
        const toggle = frame.locator('[data-visit-captures] [data-visit-captures-toggle]');
        await expect(toggle).toHaveCount(1);
        const toggleBox = await toggle.boundingBox();
        const frameBox = await frame.boundingBox();
        expect((toggleBox?.y ?? 0) + (toggleBox?.height ?? 0)).toBeLessThanOrEqual((frameBox?.y ?? 0) + (frameBox?.height ?? 0) + 0.5);
        if (shots) await item.screenshot({ path: `${shots}/explorer-card-collapsed-${theme}.png` });

        // A single capture keeps the plain card: all four corners, no footer.
        const single = page.locator('[data-explorer-visit="single"]');
        await expectOneOutline(single);
        await expect(single.locator('[data-visit-captures]')).toHaveCount(0);

        // The record and the captures are separate actions: the bar is not under the card's link.
        await toggle.scrollIntoViewIfNeeded();
        const hit = await toggle.evaluate(node => {
            const rect = node.getBoundingClientRect();
            const top = document.elementFromPoint(rect.left + rect.width / 2, rect.top + rect.height / 2);
            return node === top || node.contains(top);
        });
        expect(hit).toBe(true);
        const restingFrame = await frame.boundingBox();
        await toggle.click();
        await expect(toggle).toHaveAttribute('aria-expanded', 'true');
        await expect(page.getByRole('dialog')).toHaveCount(0);
        await expect(frame.locator('[data-visit-capture]')).toHaveCount(3);
        await expectOneOutline(item);
        const expandedFrame = await frame.boundingBox();
        expect(expandedFrame?.height).toBe(restingFrame?.height);
        await expect(frame.locator('[data-visit-captures-floating]')).toBeVisible();
        if (shots) await page.screenshot({ path: `${shots}/explorer-card-expanded-${theme}.png` });
        await page.keyboard.press('Escape');
        await expect(toggle).toHaveAttribute('aria-expanded', 'false');
        expect(errors).toEqual([]);
    });
}

test('keyboard focus is visible on the card and on its captures bar, each inside the one outline', async ({ page }) => {
    const errors = await openExplorer(page);
    const item = page.locator('[data-explorer-visit="first"]');
    const frame = item.locator('[data-detection-card]');
    const open = frame.getByRole('button', { name: 'Dunnock detected at birdcam' });
    // Set keyboard modality before focusing; native Safari tab order can skip buttons.
    await page.keyboard.press('Tab');
    await open.focus();
    await expect(open).toBeFocused();
    // The card clips its overflow to its rounded frame, so an outer ring would be cut away entirely.
    expect(await open.evaluate(node => getComputedStyle(node).boxShadow)).toContain('inset');
    if (shots) await item.screenshot({ path: `${shots}/explorer-card-focus-record.png` });
    const toggle = frame.locator('[data-visit-captures-toggle]');
    await toggle.focus();
    await expect(toggle).toBeFocused();
    expect(await toggle.evaluate(node => getComputedStyle(node).boxShadow)).not.toBe('none');
    // The ring is drawn inside the toggle, so the frame's rounded clip cannot cut it off.
    expect(await toggle.evaluate(node => getComputedStyle(node).boxShadow)).toContain('inset');
    if (shots) await item.screenshot({ path: `${shots}/explorer-card-focus.png` });
    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(page.getByRole('dialog')).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('selection switches to individual captures and keeps one card outline', async ({ page }) => {
    const errors = await openExplorer(page);
    const raw = page.waitForResponse(response => new URL(response.url()).pathname === '/api/events');
    await page.getByRole('button', { name: 'Multi-select' }).click();
    await raw;
    const item = page.locator('[data-detection-card]').filter({ has: page.getByRole('button', { name: 'Dunnock detected at birdcam' }) }).first().locator('..').locator('..');
    const frame = item.locator('[data-detection-card]');
    await frame.getByRole('button', { name: /Select|Dunnock detected at birdcam/ }).first().click();
    await expect.poll(() => frame.evaluate(node => getComputedStyle(node).borderTopWidth)).toBe('2px');
    await expectOneOutline(item);
    await expect(frame.locator('[data-visit-captures-toggle]')).toHaveCount(0);
    if (shots) await item.screenshot({ path: `${shots}/explorer-card-selected.png` });
    expect(errors).toEqual([]);
});

for (const theme of ['light', 'dark']) {
    test(`phone width keeps one outline, collapsed and expanded (${theme})`, async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 1400 });
        const errors = await openExplorer(page, `&theme=${theme}`);
        const item = page.locator('[data-explorer-visit="first"]');
        await expectOneOutline(item);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        if (shots) await item.screenshot({ path: `${shots}/explorer-card-mobile-collapsed-${theme}.png` });
        const next = page.locator('[data-explorer-visit="single"]');
        const before = await next.boundingBox();
        await item.locator('[data-visit-captures-toggle]').click();
        await expect(item.locator('[data-visit-capture]')).toHaveCount(3);
        await expectOneOutline(item);
        const after = await next.boundingBox();
        expect(after?.y).toBe(before?.y);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        if (shots) await page.screenshot({ path: `${shots}/explorer-card-mobile-expanded-${theme}.png` });
        expect(errors).toEqual([]);
    });
}
