import { test, expect, type Page } from '@playwright/test';

// Isolate layout from the external font service. app.css @imports it and WebKit applies no app
// styles until it answers, so a slow answer left the modal mounted and observed unstyled; the
// restyle then reported a ResizeObserver loop.
async function withoutWebFonts(page: Page): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
}

for (const font of ['system', 'wide fallback'] as const) {
    test(`German capture details reflow at 320px and 200% text with owner controls and long labels (${font} font)`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 320, height: 740 });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
        const errors: string[] = [];
        page.on('pageerror', error => errors.push(error.message));
        await withoutWebFonts(page);
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
            if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
            return route.fulfill({ json: {} });
        });
        // Actual modal; HTTP and media boundaries are fixtures, not backend/inference E2E.
        await page.goto('/browser-tests/modal-text-layout.html');
        const modal = page.locator('[data-detection-detail-modal]');
        await expect(modal).toBeVisible();
        // Keep the platform font case and also exercise wider fallback glyphs, which exposed the
        // anonymous flex text item's intrinsic width on Linux.
        await page.addStyleTag({ content: 'html{font-size:200%!important}'
            + (font === 'wide fallback' ? ' [data-detection-confirm]{font-family:monospace!important}' : '') });
        await expect(modal.locator('[data-counted-birds-state="not-counted"]')).toBeVisible();
        await expect(modal.getByRole('button', { name: 'Diesen Besuch dauerhaft löschen' })).toHaveCount(1);
        await expect(modal.getByRole('button', { name: /^(Erkennung ausblenden|Ausblenden)$/ })).toHaveCount(1);
        const technical = modal.locator('[data-detection-technical-identity]');
        await technical.locator('summary').click();
        await expect(technical).toHaveAttribute('open', '');
        const geometry = await modal.evaluate(element => ({
            modalWidth: element.clientWidth,
            overflowing: [...element.querySelectorAll<HTMLElement>('*')].filter(node => {
                const overflow = getComputedStyle(node).overflowX;
                return overflow !== 'hidden' && node.scrollWidth > node.clientWidth + 1;
            }).map(node => ({ tag: node.tagName, class: node.className, width: node.clientWidth, scroll: node.scrollWidth, text: node.textContent?.trim().slice(0, 100) })),
            controls: [...element.querySelectorAll<HTMLElement>('button, summary')].filter(node =>
                node.offsetParent !== null && getComputedStyle(node).visibility !== 'hidden'
            ).map(node => ({
                name: node.getAttribute('aria-label') ?? node.getAttribute('title') ?? node.textContent?.trim(),
                width: node.getBoundingClientRect().width, height: node.getBoundingClientRect().height
            }))
        }));
        await testInfo.attach('layout-geometry', { body: JSON.stringify(geometry, null, 2), contentType: 'application/json' });
        await page.screenshot({ path: testInfo.outputPath('german-modal-320-200.png'), fullPage: true });
        expect(geometry.overflowing).toEqual([]);
        for (const control of geometry.controls) {
            expect(control.width, `${control.name} width`).toBeGreaterThanOrEqual(44);
            expect(control.height, `${control.name} height`).toBeGreaterThanOrEqual(44);
        }
        expect(errors).toEqual([]);
    });
}

test('text reflow keeps the whole-scene peek on full-resolution pixels and its crop outline aligned', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await withoutWebFonts(page);
    const fullId = 'layout__full_frame__f150__fixture';
    const cropId = 'layout__model_crop__f150__fixture';
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: {
            current_source: 'hq_candidate_model_crop', current_candidate_id: cropId, birds: [],
            candidates: [
                { candidate_id: fullId, source_mode: 'full_frame', clip_variant: 'event', frame_index: 150,
                    ranking_score: 0.8, selected: false, image_url: '/api/layout-full/image.jpg', thumbnail_url: '/api/layout-full/thumbnail.jpg' },
                { candidate_id: cropId, source_mode: 'model_crop', clip_variant: 'event', frame_index: 150,
                    ranking_score: 0.9, selected: true, crop_box: [100, 100, 250, 250],
                    image_url: '/api/layout-crop/image.jpg', thumbnail_url: '/api/layout-crop/thumbnail.jpg' }
            ]
        } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: {
            available: true, high_quality_bird_crop_enabled: true, source: 'hq_candidate_model_crop'
        } });
        if (path.endsWith('.jpg')) {
            const [width, height] = path.includes('thumbnail') ? [100, 60] : path.includes('layout-crop') ? [150, 150] : [1000, 600];
            return route.fulfill({ contentType: 'image/svg+xml', body:
                `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="${width}" height="${height}" fill="#64748b"/></svg>` });
        }
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/modal-text-layout.html');
    await page.addStyleTag({ content: 'html{font-size:200%!important}' });
    const peek = page.locator('[data-detection-whole-scene-peek]');
    await peek.click();
    await expect(peek).toHaveAttribute('aria-pressed', 'true');
    const image = page.locator('[data-detection-whole-scene-image]');
    await expect(image).toHaveAttribute('src', /\/api\/layout-full\/image\.jpg/);
    await expect(page.locator('[data-detection-whole-scene-outline]')).toHaveCount(1);
    const geometry = await page.locator('[data-detection-photograph]').evaluate(element => {
        const image = element.querySelector<HTMLImageElement>('[data-detection-whole-scene-image]');
        const outline = element.querySelector<HTMLElement>('[data-detection-whole-scene-outline]');
        if (!image || !outline) throw new Error('Missing actual image or crop outline');
        const frame = element.getBoundingClientRect();
        const box = outline.getBoundingClientRect();
        const scale = Math.min(frame.width / image.naturalWidth, frame.height / image.naturalHeight);
        return { natural: [image.naturalWidth, image.naturalHeight], actual: [box.left - frame.left, box.top - frame.top, box.width, box.height],
            expected: [(frame.width - image.naturalWidth * scale) / 2 + 100 * scale,
                (frame.height - image.naturalHeight * scale) / 2 + 100 * scale, 150 * scale, 150 * scale] };
    });
    expect(geometry.natural).toEqual([1000, 600]);
    for (let index = 0; index < geometry.actual.length; index += 1) {
        expect(Math.abs(geometry.actual[index] - geometry.expected[index])).toBeLessThan(1);
    }
    expect(errors).toEqual([]);
    await testInfo.attach('whole-scene-geometry', { body: JSON.stringify(geometry), contentType: 'application/json' });
    await page.screenshot({ path: testInfo.outputPath('whole-scene-text-zoom.png'), fullPage: true });
});

test('a tall crop photograph is shown whole in the record, over its ambient fill', async ({ page }) => {
    // A woodpecker on a pole covered the photograph box as a band of feathers (#481).
    await page.setViewportSize({ width: 1280, height: 900 });
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await withoutWebFonts(page);
    const fullId = 'tall__full_frame__f150__fixture';
    const cropId = 'tall__model_crop__f150__fixture';
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: {
            current_source: 'hq_candidate_model_crop', current_candidate_id: cropId, birds: [],
            candidates: [
                { candidate_id: fullId, source_mode: 'full_frame', clip_variant: 'event', frame_index: 150,
                    ranking_score: 0.8, selected: false, image_url: '/api/tall-full/image.jpg', thumbnail_url: '/api/tall-full/thumbnail.jpg' },
                { candidate_id: cropId, source_mode: 'model_crop', clip_variant: 'event', frame_index: 150,
                    ranking_score: 0.9, selected: true, crop_box: [400, 100, 587, 393],
                    image_url: '/api/tall-crop/image.jpg', thumbnail_url: '/api/tall-crop/thumbnail.jpg' }
            ]
        } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: {
            available: true, high_quality_bird_crop_enabled: true, source: 'hq_candidate_model_crop'
        } });
        if (path.endsWith('.jpg')) {
            const [width, height] = path.includes('full') ? [1920, 1080] : path.includes('thumbnail') ? [100, 60] : [187, 293];
            return route.fulfill({ contentType: 'image/svg+xml', body:
                `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="${width}" height="${height}" fill="#64748b"/></svg>` });
        }
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/modal-text-layout.html');
    const photograph = page.locator('[data-detection-photograph] img:not([data-detection-media-ambient])').first();
    await expect(photograph).toHaveJSProperty('naturalHeight', 293);
    await expect(photograph).toHaveCSS('object-fit', 'contain');
    await expect(page.locator('[data-detection-media-ambient]')).toHaveCount(1);
    expect(errors).toEqual([]);
});
