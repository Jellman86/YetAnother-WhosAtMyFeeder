import { expect, test, type Page } from '@playwright/test';

/**
 * When the finder cannot run for a reason that stands (here: no whole frame was kept), the row under
 * the photograph steps aside so the identification follows it, and the reason is said once after the
 * identification, in a status that is always present, and as plain text in More actions.
 */
const REASON = 'More birds cannot be looked for: the whole frame behind this photograph was not kept.';

async function openRecord(page: Page): Promise<void> {
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
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/browser-tests/modal-text-layout.html?controls=true');
    await expect(page.locator('[data-detection-detail-modal]')).toBeVisible({ timeout: 15_000 });
}

test('with More actions closed, the reason is a status after the identification and the photo row steps aside', async ({ page }) => {
    await openRecord(page);
    const status = page.getByRole('status').filter({ hasText: REASON });
    await expect(status).toBeVisible();
    await expect(status).toHaveAttribute('aria-live', 'polite');
    await expect(status).toContainText('Find more birds:');
    await expect(page.locator('[data-bird-scan-control]')).toBeHidden();
    await expect(page.locator('[data-detection-scan-unavailable]')).toHaveCount(0);
    // After the identification in reading and tab order, not between it and the photograph.
    const follows = await page.evaluate(() => {
        const identity = document.querySelector('[data-detection-identity]');
        const standing = document.querySelector('[data-detection-scan-standing]');
        return Boolean(identity && standing && identity.compareDocumentPosition(standing) & Node.DOCUMENT_POSITION_FOLLOWING);
    });
    expect(follows).toBe(true);
});

test('with More actions open, the finder is listed with its reason as text, not as a disabled control', async ({ page }) => {
    await openRecord(page);
    await page.locator('[data-detection-more-actions]').click();
    const item = page.locator('[data-detection-scan-unavailable]');
    await expect(item).toBeVisible();
    await expect(item).toContainText('Find more birds');
    await expect(item).toContainText(REASON);
    await expect(item.locator('button, [aria-describedby]')).toHaveCount(0);
    // The status stays where it is, so nothing it said is lost when the menu opens.
    await expect(page.getByRole('status').filter({ hasText: REASON })).toBeVisible();
});
