import { test, expect } from '@playwright/test';

for (const [status, message] of [
    ['pending', 'Video analysis queued'],
    ['processing', 'Preparing video analysis'],
    ['observed', '3 of 7 frames read']
] as const) {
    test(`${status} video shows only observed analysis state`, async ({ page }, testInfo) => {
        const errors: string[] = [];
        page.on('pageerror', error => errors.push(error.message));
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
        await page.route(url => url.pathname.startsWith('/api/'), async route => {
            const path = new URL(route.request().url()).pathname;
            if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: {
                candidates: [], birds: [], current_source: 'frigate_snapshot'
            } });
            if (path.endsWith('/snapshot/status')) return route.fulfill({ json: {
                available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot'
            } });
            if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body:
                '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#64748b"/></svg>' });
            if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
            // A global provider is not evidence of the queued capture's execution device.
            if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true, active_provider: 'OpenVINOExecutionProvider', inference_backend: 'openvino' } });
            return route.fulfill({ json: {} });
        });
        await page.goto(`/browser-tests/modal-text-layout.html?videoStatus=${status === 'observed' ? 'processing&observedProgress=true' : status}`);
        const modal = page.locator('[data-detection-detail-modal]');
        await expect(modal).toBeVisible();
        if (status !== 'observed') await expect(modal.locator('[data-detection-photograph] img:not([data-detection-media-ambient])').first()).toBeVisible();
        await expect(modal.getByText(message, { exact: true })).toBeVisible();
        await expect(modal.getByText(/0 of \d+ frames read|Waiting for the first frame/)).toHaveCount(0);
        if (status !== 'observed') await expect(modal.getByRole('progressbar')).toHaveCount(0);
        else await expect(modal.getByRole('progressbar', { name: 'Video frames read' })).toBeVisible();
        if (status !== 'observed' && (page.viewportSize()?.width ?? 0) >= 640) {
            await expect(modal.locator('[data-detection-media-title]')).toBeVisible();
        }
        expect(errors).toEqual([]);
        if (status === 'pending') await page.screenshot({ path: testInfo.outputPath('queued-photograph.png'), fullPage: true });
    });
}
