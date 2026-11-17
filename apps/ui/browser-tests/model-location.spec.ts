import { test, expect } from '@playwright/test';

for (const width of [1280, 390]) {
    test(`location guidance preserves unsaved detection settings at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 900 });
        const errors: string[] = [];
        page.on('pageerror', error => errors.push(error.message));
        let settingsReads = 0;
        const model = {
            id: 'location-fixture', name: 'Location-aware wildlife', description: 'Fixture classifier',
            tier: 'large', status: 'experimental', taxonomy_scope: 'wildlife_wide',
            artifact_kind: 'classifier', runtime: 'onnx', estimated_ram_mb: 2048,
            file_size_mb: 456, supported_inference_providers: ['cpu'],
            preprocessing: { metadata_input: 'inat2021_location_v1' }
        };
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
        await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
            const path = new URL(route.request().url()).pathname;
            if (path === '/api/settings') {
                settingsReads++;
                return route.fulfill({ json: {
                    frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
                    mqtt_auth: false, classification_threshold: 0.6
                } });
            }
            if (path === '/api/models/available') return route.fulfill({ json: [model] });
            if (path === '/api/models/installed') return route.fulfill({ json: [{
                id: model.id, metadata: model, ready: true, reason: 'ready',
                is_active: true, validated: true
            }] });
            if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
            if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
            if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
            return route.fulfill({ json: {} });
        });
        await page.goto('/browser-tests/settings-backfill.html');
        // Detection and Models are both parts of Identifying birds; the second open is a no-op there.
        const openTab = async (_part: 'detection' | 'models', name: string) => {
            if (width < 1024) await page.getByRole('combobox', { name: 'Settings section', exact: true }).selectOption('identification');
            else await page.getByRole('link', { name, exact: true }).click();
        };
        // An unsaved edit in Detection, then the model's location guidance in Models.
        await openTab('detection', 'Identifying birds');
        const slider = page.locator('#confidence-threshold-slider');
        await expect(slider).toHaveValue('0.6');
        await slider.fill('0.75');
        await openTab('models', 'Identifying birds');
        const location = page.getByRole('link', { name: 'Open location settings', exact: true });
        await expect(location).toBeVisible();
        await expect(location).toHaveAttribute('href', '/settings/integrations');
        await expect(page.getByText('Uses your feeder location', { exact: true })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await location.scrollIntoViewIfNeeded();
        await page.screenshot({ path: testInfo.outputPath('model-location.png') });
        const readsBeforeLink = settingsReads;
        await location.click();
        if (width < 768) {
            await expect(page.getByRole('combobox', { name: 'Settings section', exact: true })).toHaveValue('sharing');
        } else {
            await expect(page.getByRole('link', { name: 'Sharing & integrations', exact: true })).toHaveAttribute('aria-current', 'page');
        }
        await openTab('detection', 'Identifying birds');
        await expect(slider).toHaveValue('0.75');
        expect(settingsReads).toBe(readsBeforeLink);
        expect(errors).toEqual([]);
    });
}
