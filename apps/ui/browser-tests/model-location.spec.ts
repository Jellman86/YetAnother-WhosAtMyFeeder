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
        if (width < 768) await page.getByRole('combobox', { name: 'Settings', exact: true }).selectOption('detection');
        else await page.getByRole('link', { name: 'Detection', exact: true }).click();
        const slider = page.locator('#confidence-threshold-slider');
        await expect(slider).toHaveValue('0.6');
        await slider.fill('0.75');
        const location = page.getByRole('link', { name: 'Open Location settings', exact: true });
        await expect(location).toBeVisible();
        await expect(location).toHaveAttribute('href', '/settings/integrations');
        await expect(page.getByText('Uses your feeder location', { exact: true })).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
        await location.scrollIntoViewIfNeeded();
        await page.screenshot({ path: testInfo.outputPath('model-location.png') });
        const readsBeforeLink = settingsReads;
        await location.click();
        if (width < 768) {
            await expect(page.getByRole('combobox', { name: 'Settings', exact: true })).toHaveValue('integrations');
            await page.getByRole('combobox', { name: 'Settings', exact: true }).selectOption('detection');
        } else {
            await expect(page.getByRole('link', { name: 'Integrations', exact: true })).toHaveAttribute('aria-current', 'page');
            await page.getByRole('link', { name: 'Detection', exact: true }).click();
        }
        await expect(slider).toHaveValue('0.75');
        expect(settingsReads).toBe(readsBeforeLink);
        expect(errors).toEqual([]);
    });
}
