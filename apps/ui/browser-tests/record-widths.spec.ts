import { expect, test, type Page } from '@playwright/test';

/**
 * The record uses the space each device gives it. On a phone the photograph's own buttons sit on its
 * lower edge, so no black band separates the photograph from the identification. From 1280 px the
 * reference for the species stands in a side column beside the identification. On a short landscape
 * screen the photograph gives up height, and every action stays reachable.
 */
async function openRecord(page: Page, size: { width: number; height: number }): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="3"/>' });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.setViewportSize(size);
    await page.goto('/browser-tests/modal-text-layout.html?controls=true');
    await expect(page.locator('[data-detection-detail-modal]')).toBeVisible({ timeout: 15_000 });
}

async function noSidewaysScroll(page: Page): Promise<void> {
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
}

test('on a phone the photograph\'s buttons sit on its lower edge, with no band under it', async ({ page }) => {
    await openRecord(page, { width: 390, height: 844 });
    const photo = await page.locator('[data-detection-photograph]').boundingBox();
    const actions = page.locator('[data-detection-media-actions]');
    await expect(actions).toBeVisible();
    const buttons = await actions.boundingBox();
    expect(photo && buttons).toBeTruthy();
    if (!photo || !buttons) return;
    // The buttons are inside the photograph's frame, along its bottom.
    expect(buttons.y).toBeGreaterThanOrEqual(photo.y);
    expect(buttons.y + buttons.height).toBeLessThanOrEqual(photo.y + photo.height + 1);
    // Under the photograph the footer holds only what it really shows (the visit's frames, the finder),
    // not a band for the buttons.
    const band = await page.locator('[data-detection-media-footer]').evaluate((footer) => {
        const kept = [...footer.querySelectorAll('[data-detection-inline-frame-picker], [data-bird-scan-control]')]
            .reduce((sum, part) => sum + part.getBoundingClientRect().height, 0);
        return footer.getBoundingClientRect().height - kept;
    });
    expect(band).toBeLessThan(8);
    await noSidewaysScroll(page);
});

test('from 1280 px the species reference stands beside the identification; below, it follows it', async ({ page }) => {
    await openRecord(page, { width: 1440, height: 900 });
    const primary = await page.locator('[data-detection-primary-column]').boundingBox();
    const secondary = await page.locator('[data-detection-secondary-column]').boundingBox();
    expect(primary && secondary && secondary.x >= primary.x + primary.width - 1).toBe(true);
    expect(primary && secondary && Math.abs(secondary.y - primary.y)).toBeLessThan(2);
    // The record takes the room: wider than the 1024 px it was held to.
    const dialog = await page.locator('[data-detection-detail-modal] [role="document"]').first().boundingBox();
    expect(dialog?.width ?? 0).toBeGreaterThan(1100);
    await noSidewaysScroll(page);

    await page.setViewportSize({ width: 1024, height: 768 });
    const narrowPrimary = await page.locator('[data-detection-primary-column]').boundingBox();
    const narrowSecondary = await page.locator('[data-detection-secondary-column]').boundingBox();
    expect(narrowPrimary && narrowSecondary && narrowSecondary.y >= narrowPrimary.y + narrowPrimary.height - 1).toBe(true);
});

for (const size of [{ width: 1280, height: 600 }, { width: 1440, height: 640 }, { width: 1024, height: 600 }, { width: 844, height: 390 }]) {
    test(`at ${size.width} × ${size.height} the close button is in view and every identification action can be reached`, async ({ page }) => {
        await openRecord(page, size);
        await expect(page.locator('[data-detection-modal-close]')).toBeInViewport({ ratio: 1 });
        // Held sideways the photograph and the identification stand side by side, so the identification
        // is on the first screen, beside the photograph rather than under it.
        await expect(page.locator('[data-detection-identity]')).toBeInViewport();
        const photo = await page.locator('[data-detection-photograph]').boundingBox();
        const identity = await page.locator('[data-detection-identity]').boundingBox();
        expect(photo && identity && identity.x >= photo.x + photo.width - 1).toBe(true);
        for (const selector of ['[data-detection-confirm]', '[data-detection-pick]', '[data-detection-more-actions]']) {
            const action = page.locator(selector);
            if (await action.count() === 0) continue;
            await action.scrollIntoViewIfNeeded();
            // Scrolled to, the action shows whole but for the dialog's rounded border.
            await expect(action, selector).toBeInViewport({ ratio: 0.95 });
        }
        await noSidewaysScroll(page);
    });
}

test('on a wide screen the photograph keeps its shape at the top of its column, with no black band above or below it', async ({ page }) => {
    await openRecord(page, { width: 1920, height: 1080 });
    const photo = await page.locator('[data-detection-photograph]').boundingBox();
    const column = await page.locator('[data-detection-photograph]').evaluate((node) => {
        const box = node.parentElement?.getBoundingClientRect();
        return box ? { x: box.x, y: box.y, width: box.width, height: box.height } : null;
    });
    expect(photo && column).toBeTruthy();
    if (!photo || !column) return;
    // 16:9 at the column's width, not stretched to the column's height.
    expect(Math.abs(photo.height - photo.width * 9 / 16)).toBeLessThan(3);
    expect(Math.abs(photo.y - column.y)).toBeLessThan(2);
    // What is left of a tall column is the page's own ground, not black.
    const ground = await page.locator('[data-detection-photograph]').evaluate((node) => getComputedStyle(node.parentElement as Element).backgroundColor);
    const black = await page.locator('[data-detection-photograph]').evaluate((node) => getComputedStyle(node).backgroundColor);
    expect(ground).not.toBe(black);
});

test('on a phone the visit\'s frames and the finder come after the identification, not between it and the photograph', async ({ page }) => {
    await openRecord(page, { width: 390, height: 844 });
    const order = await page.evaluate(() => {
        const identity = document.querySelector('[data-detection-identity]');
        const strip = document.querySelector('[data-detection-inline-frame-picker]');
        return Boolean(identity && strip && identity.compareDocumentPosition(strip) & Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(order).toBe(true);
    await expect(page.locator('[data-detection-media-footer] [data-detection-inline-frame-picker]')).toHaveCount(0);
    // Taps on the photograph beside the buttons reach the photograph.
    const row = page.locator('[data-detection-media-actions]');
    expect(await row.evaluate((node) => getComputedStyle(node).pointerEvents)).toBe('none');
    // Turned to a desktop width, the frames return under the photograph.
    await page.setViewportSize({ width: 1440, height: 900 });
    await expect(page.locator('[data-detection-media-footer] [data-detection-inline-frame-picker]')).toHaveCount(1);
    await expect(page.locator('[data-detection-stacked-strip]')).toHaveCount(0);
});

