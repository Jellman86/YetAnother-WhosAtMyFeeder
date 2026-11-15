import { expect, test, type Page } from '@playwright/test';

/**
 * CLAUDE.md §5: media degrades silently to a placeholder and never shifts layout. A picture that
 * fails must keep its box and show neither its alt text nor the browser's broken-image glyph.
 */
const pixel = '<svg xmlns="http://www.w3.org/2000/svg" width="600" height="200"><rect width="600" height="200" fill="#2a3a4a"/></svg>';
const audioContext = [{
    id: 1, birdnet_id: 42, species: 'Dunnock', scientific_name: 'Prunella modularis', confidence: 0.82,
    timestamp: '2026-10-01T12:00:05Z', offset_seconds: 5, sensor_id: 'garden-mic'
}];

async function openRecord(page: Page, imagesFail: boolean): Promise<void> {
    await page.setViewportSize({ width: 1280, height: 900 });
    page.on('pageerror', error => { throw error; });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.startsWith('/api/audio/context/')) return route.fulfill({ json: audioContext });
        if (path.startsWith('/api/audio/spectrogram/') || path.endsWith('.jpg') || path.includes('/snapshot') || path.includes('/thumbnail')) {
            if (imagesFail) return route.fulfill({ status: 404, contentType: 'text/plain', body: 'gone' });
            if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
            if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, source: 'frigate_snapshot' } });
            return route.fulfill({ contentType: 'image/svg+xml', body: pixel });
        }
        // A reference picture and summary for the species, whose picture fails with the rest.
        if (path.startsWith('/api/species/') && path.endsWith('/info')) return route.fulfill({ json: { title: 'Dunnock', extract: 'A small brown bird.', thumbnail_url: '/api/reference/dunnock.jpg', source: 'Wikipedia' } });
        if (path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/modal-text-layout.html?controls=true');
    await expect(page.locator('[data-detection-detail-modal]')).toBeVisible({ timeout: 15000 });
}

/** Every picture inside `scope` that failed: whether its alt text or glyph can be seen. */
async function visibleFailures(page: Page): Promise<string[]> {
    return page.locator('[data-detection-detail-modal] img').evaluateAll(images =>
        images
            .filter(image => image instanceof HTMLImageElement && image.complete && image.naturalWidth === 0 && image.getAttribute('src'))
            .filter(image => getComputedStyle(image).visibility !== 'hidden' && image.getBoundingClientRect().width > 0)
            .map(image => `${image.getAttribute('alt') ?? ''} (${image.getAttribute('src')})`)
    );
}

test('a spectrogram that fails keeps its box, shows a quiet placeholder and keeps the call playable', async ({ page }) => {
    await openRecord(page, false);
    const box = page.locator('[data-record-spectrogram]');
    await expect(box.locator('img')).toBeVisible();
    await expect.poll(() => box.locator('img').evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
    const loaded = await box.boundingBox();

    await page.unrouteAll({ behavior: 'ignoreErrors' });
    await openRecord(page, true);
    const failed = page.locator('[data-record-spectrogram]');
    await expect(failed.locator('[data-record-spectrogram-unavailable]')).toBeVisible();
    await expect(failed.locator('img')).toHaveCount(0);
    await expect(failed).not.toContainText('BirdNET-Go spectrogram for the matched audio detection');
    const missing = await failed.boundingBox();
    expect(missing?.height).toBe(loaded?.height);
    expect(missing?.width).toBe(loaded?.width);
    // The picture is gone; the call is not.
    await expect(page.getByRole('button', { name: 'Play audio clip' })).toBeVisible();
    expect(await failed.evaluate(node => node.scrollWidth <= node.clientWidth + 1 && node.scrollHeight <= node.clientHeight + 1)).toBe(true);
});

test('no picture in the record shows its alt text or a broken-image glyph when it fails', async ({ page }) => {
    await openRecord(page, true);
    await expect(page.locator('[data-record-spectrogram-unavailable]')).toBeVisible();
    await page.waitForLoadState('networkidle');
    expect(await visibleFailures(page)).toEqual([]);
});
