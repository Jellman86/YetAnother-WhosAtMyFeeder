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
        // The record is a lazy chunk on a dev server; a loaded host can take longer than the default wait.
        await expect(modal).toBeVisible({ timeout: 15_000 });
        // Keep the platform font case and also exercise wider fallback glyphs, which exposed the
        // anonymous flex text item's intrinsic width on Linux.
        await page.addStyleTag({ content: 'html{font-size:200%!important}'
            + (font === 'wide fallback' ? ' [data-detection-confirm]{font-family:monospace!important}' : '') });
        await expect(modal.locator('[data-counted-birds-state="not-counted"]')).toBeVisible();
        await modal.locator('[data-detection-more-actions]').click();
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

test('the record is walked by keyboard in the order it is read', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await withoutWebFonts(page);
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot' } });
        if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body:
            '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#64748b"/></svg>' });
        if (path.startsWith('/api/species/') && path.endsWith('/info')) return route.fulfill({ json: {
            title: 'Dunnock', extract: 'The dunnock is a small passerine. '.repeat(40), summary_source: 'Wikipedia',
            summary_source_url: 'https://en.wikipedia.org/wiki/Dunnock'
        } });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/modal-text-layout.html?controls=true');
    const modal = page.locator('[data-detection-detail-modal]');
    await expect(modal.locator('[data-detection-confirm]')).toBeVisible();
    await expect(modal.locator('[data-detection-reference-link]')).toBeVisible();

    // One close button, in a strip nothing scrolls under.
    await expect(modal.locator('[data-dialog-close]')).toHaveCount(1);

    // The long article is a few lines and a link, below every decision.
    const referenceText = modal.locator('[data-detection-reference-text]');
    expect((await referenceText.boundingBox())!.height).toBeLessThan(90);
    const confirmTop = (await modal.locator('[data-detection-confirm]').boundingBox())!.y;
    expect(confirmTop).toBeLessThan((await referenceText.boundingBox())!.y);

    // More actions is a list drawn whole under its trigger at desktop width: every row is on screen
    // inside the list's own box and can be clicked. The scrolling column once squashed the list.
    await modal.locator('[data-detection-more-actions]').click();
    const panel = modal.locator('[data-detection-more-actions-panel]');
    const rows = panel.getByRole('button');
    expect(await rows.count()).toBeGreaterThanOrEqual(3);
    const panelBox = (await panel.boundingBox())!;
    for (const row of await rows.all()) {
        await expect(row).toBeVisible();
        const rowBox = (await row.boundingBox())!;
        expect(rowBox.y).toBeGreaterThanOrEqual(panelBox.y - 1);
        expect(rowBox.y + rowBox.height).toBeLessThanOrEqual(panelBox.y + panelBox.height + 1);
    }
    await modal.locator('[data-detection-delete]').click({ trial: true });
    await modal.locator('[data-detection-more-actions]').click();
    await expect(panel).toHaveCount(0);

    // Walk every stop in the details column and record where each one is drawn.
    await modal.locator('[data-dialog-close]').focus();
    const stops: { name: string; top: number; column: boolean }[] = [];
    for (let step = 0; step < 60; step += 1) {
        await page.keyboard.press('Tab');
        const stop = await page.evaluate(() => {
            const active = document.activeElement as HTMLElement | null;
            if (!active || active === document.body) return null;
            active.scrollIntoView({ block: 'nearest' });
            const column = active.closest('[data-detection-details-column]');
            return {
                name: (active.getAttribute('aria-label') ?? active.textContent ?? '').trim().slice(0, 60),
                // Position inside the scrolling column, so scrolling does not disturb the order.
                top: column ? active.getBoundingClientRect().top - column.getBoundingClientRect().top + column.scrollTop : -1,
                column: column !== null
            };
        });
        if (!stop) break;
        if (stops.some(seen => seen.name === stop.name && seen.top === stop.top)) break;
        stops.push(stop);
    }
    const column = stops.filter(stop => stop.column);
    expect(column.length).toBeGreaterThan(4);
    for (let index = 1; index < column.length; index += 1) {
        expect(column[index].top, `"${column[index].name}" follows "${column[index - 1].name}"`).toBeGreaterThanOrEqual(column[index - 1].top - 1);
    }
    // The identifiers are the last thing read and the last thing reached.
    expect(column.at(-1)!.name).toContain('Detection ID');
});

for (const [language, noted] of [['de', true], ['en', false]] as const) {
    test(`a description in ${language} ${noted ? 'is labelled and marked with its language' : 'needs no label in an English page'}`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await withoutWebFonts(page);
        await page.route(url => url.pathname.startsWith('/api/'), async route => {
            const path = new URL(route.request().url()).pathname;
            if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
            if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot' } });
            if (path.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body:
                '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#64748b"/></svg>' });
            if (path.startsWith('/api/species/') && path.endsWith('/info')) return route.fulfill({ json: {
                title: 'Heckenbraunelle', extract: 'Die Heckenbraunelle ist eine Vogelart.', summary_source: 'Wikipedia',
                summary_source_url: `https://${language}.wikipedia.org/wiki/Heckenbraunelle`, summary_language: language
            } });
            if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
            if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
            return route.fulfill({ json: {} });
        });
        await page.goto('/browser-tests/modal-text-layout.html?controls=true');
        const modal = page.locator('[data-detection-detail-modal]');
        const text = modal.locator('[data-detection-reference-text]');
        await expect(text).toBeVisible();
        const note = modal.locator('[data-reference-summary-language]');
        if (noted) {
            // The page is read in English and the description is German: said in words, and marked
            // so a screen reader reads it in a German voice.
            await expect(text).toHaveAttribute('lang', 'de');
            await expect(note).toHaveText('Description from German Wikipedia');
            await note.scrollIntoViewIfNeeded();
            await page.screenshot({ path: testInfo.outputPath('description-in-another-language.png') });
        } else {
            await expect(note).toHaveCount(0);
            expect(await text.getAttribute('lang')).toBeNull();
        }
    });
}
