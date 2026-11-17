import { expect, test, type Page, type Route } from '@playwright/test';

/**
 * The AI note belongs to one identification. A failed request, or one still on its way, must not
 * outlive a change of species: the record then offers a fresh analysis of the bird it now names.
 */
const EVENT = 'long-camera-capture-abcdefghijklmnopqrstuvwxyz-0123456789';
const RENAMED = {
    status: 'updated', new_species: 'Dunnock', category_name: 'Prunella modularis', scientific_name: 'Prunella modularis',
    common_name: 'Dunnock', taxa_id: 13858, manual_tagged: true, photo_changed: false
};

async function openRecord(page: Page, analyse: (route: Route) => Promise<void>): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path === `/api/events/${EVENT}/analyze`) return analyse(route);
        if (path === `/api/events/${EVENT}` && route.request().method() === 'PATCH') return route.fulfill({ json: RENAMED });
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="3"/>' });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/modal-text-layout.html?ai=true');
    await expect(page.locator('[data-detection-detail-modal]')).toBeVisible({ timeout: 15_000 });
}

test('a failed analysis is dropped when the species changes, and a fresh one is offered', async ({ page }) => {
    await openRecord(page, (route) => route.fulfill({ status: 500, json: { detail: 'The model is offline' } }));
    await page.getByRole('button', { name: 'Ask the AI naturalist' }).click();
    await expect(page.getByText(/^Error:/)).toBeVisible();
    await expect(page.getByRole('button', { name: 'Regenerate analysis' })).toBeVisible();

    await page.locator('[data-detection-confirm]').click();
    await expect(page.locator('#detection-modal-title')).toHaveText('Dunnock');
    await expect(page.getByText(/^Error:/)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Regenerate analysis' })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Ask the AI naturalist' })).toBeVisible();
});

test('an analysis still on its way when the species changes is not shown for the new species', async ({ page }) => {
    let answer: (() => void) | undefined;
    const answered = new Promise<void>((resolve) => { answer = resolve; });
    let release: (() => void) | undefined;
    const held = new Promise<void>((resolve) => { release = resolve; });
    await openRecord(page, async (route) => {
        await held;
        await route.fulfill({ json: { analysis: 'A note about the Great Tit.', analysis_timestamp: '2026-11-17T09:00:00Z' } });
        answer?.();
    });
    await page.getByRole('button', { name: 'Ask the AI naturalist' }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Analyzing behavior' })).toBeVisible();

    await page.locator('[data-detection-confirm]').click();
    await expect(page.locator('#detection-modal-title')).toHaveText('Dunnock');
    release?.();
    await answered;
    await expect(page.getByText('A note about the Great Tit.')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Ask the AI naturalist' })).toBeVisible();
});
