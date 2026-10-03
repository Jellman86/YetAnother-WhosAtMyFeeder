import { test, expect, type Page, type Route } from '@playwright/test';

// Boundary fixture: /api is mocked here and scenes are synthetic SVGs with a declared pixel size.
// These tests check rendering, geometry and state handling, not inference or retained media.

function svgScene(width: number, height: number, boxes: number[][]): string {
    const marks = boxes.map(([left, top, right, bottom]) =>
        `<rect x="${left}" y="${top}" width="${right - left}" height="${bottom - top}" fill="#fca5a5"/>`).join('');
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"><rect width="${width}" height="${height}" fill="#334155"/>${marks}</svg>`;
}

const CARDINAL_BOXES = [[858, 1151, 967, 1352], [1454, 1265, 1642, 1494]];

interface Fixture {
    patch?: (route: Route, change: Record<string, unknown>, birdId: number) => Promise<void>;
    slowScene?: Promise<void>;
    requests: string[];
}

async function open(page: Page, query: string, fixture: Fixture = { requests: [] }, waitUntil: 'load' | 'domcontentloaded' = 'load'): Promise<Fixture> {
    // Isolate layout from the external font service. A web font swapping in late moved the phone
    // list 40px between mouse down and up, so a click reached neither row.
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        fixture.requests.push(`${route.request().method()} ${path}`);
        const patch = /^\/api\/frigate\/fixture-event\/birds\/(\d+)$/.exec(path);
        if (path === '/api/species/search') {
            await route.fulfill({ json: [{ id: 'Northern Cardinal', display_name: 'Northern Cardinal', common_name: 'Northern Cardinal', scientific_name: null }] });
        } else if (path === '/api/fixture/scene-3840.svg') {
            await route.fulfill({ contentType: 'image/svg+xml', body: svgScene(3840, 2160, CARDINAL_BOXES) });
        } else if (path === '/api/fixture/scene-960.svg') {
            await route.fulfill({ contentType: 'image/svg+xml', body: svgScene(960, 540, []) });
        } else if (path === '/api/fixture/scene-1920.svg') {
            await route.fulfill({ contentType: 'image/svg+xml', body: svgScene(1920, 1080, [[400, 300, 700, 600]]) });
        } else if (path === '/api/fixture/scene-slow.svg') {
            await fixture.slowScene;
            await route.fulfill({ contentType: 'image/svg+xml', body: svgScene(800, 450, []) }).catch(() => undefined);
        } else if (path === '/api/fixture/missing.svg') {
            await route.fulfill({ status: 404, body: '' });
        } else if (path.startsWith('/api/frigate/') && path.endsWith('thumbnail.jpg')) {
            await route.fulfill({ contentType: 'image/svg+xml', body: svgScene(64, 64, []) });
        } else if (patch && route.request().method() === 'PATCH' && fixture.patch) {
            await fixture.patch(route, route.request().postDataJSON(), Number(patch[1]));
        } else {
            throw new Error(`Unexpected fixture API request: ${route.request().method()} ${path}`);
        }
    });
    page.on('pageerror', error => { throw error; });
    await page.goto(`/browser-tests/counted-birds.html?${query}`, { waitUntil });
    return fixture;
}

function cardinalBird(id: number, change: Record<string, unknown>) {
    const unknown = id === 3;
    return {
        id, bird_index: id - 1, candidate_id: `fixture__full_frame__f150__abc__observed__${id}`, clip_variant: 'event', frame_index: 150,
        crop_box: unknown ? CARDINAL_BOXES[0] : CARDINAL_BOXES[1], detector_confidence: unknown ? 0.19 : 0.86,
        species: (change.species as string | undefined) ?? (unknown ? 'Unknown Bird' : 'Cardinalis cardinalis'),
        classifier_label: unknown ? 'Poecile hudsonicus' : 'Cardinalis cardinalis', classifier_score: unknown ? 0.27 : 0.69,
        manual_species: change.species !== undefined, is_hidden: (change.is_hidden as boolean | undefined) ?? false
    };
}

async function targetsAreUsable(page: Page): Promise<void> {
    const bounds = await page.locator('[data-counted-birds] button, [data-dashboard-field-log] button').evaluateAll(nodes =>
        nodes.filter(node => (node as HTMLElement).offsetParent !== null)
            .map(node => ({ ...node.getBoundingClientRect().toJSON(), label: node.textContent?.trim() })));
    for (const target of bounds) {
        expect(target.width, `${target.label} width`).toBeGreaterThanOrEqual(44);
        expect(target.height, `${target.label} height`).toBeGreaterThanOrEqual(44);
    }
    for (let a = 0; a < bounds.length; a += 1) for (let b = a + 1; b < bounds.length; b += 1) {
        const overlapX = Math.min(bounds[a].right, bounds[b].right) - Math.max(bounds[a].left, bounds[b].left);
        const overlapY = Math.min(bounds[a].bottom, bounds[b].bottom) - Math.max(bounds[a].top, bounds[b].top);
        expect(overlapX > .5 && overlapY > .5, `${bounds[a].label} overlaps ${bounds[b].label}`).toBe(false);
    }
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

test('outlines the exact count frame, not the portrait frame, on the image content box', async ({ page }, testInfo) => {
    const fixture = await open(page, 'case=cardinal');
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(2);
    expect(fixture.requests).not.toContain('GET /api/fixture/f75.svg');
    expect(fixture.requests).not.toContain('GET /api/fixture/portrait.svg');
    await expect(page.locator('[data-counted-birds-provenance]')).toContainText('frame 150 of the event clip');
    await expect(page.locator('[data-counted-birds-provenance]')).toContainText('different frame');

    // Read both rectangles in one layout snapshot. A font swap between separate
    // browser round trips can move both together and falsify their relative position.
    const { image, cardinal } = await page.locator('[data-counted-birds-frame]').evaluate(frame => {
        const image = frame.querySelector('img');
        const cardinal = frame.querySelector('[data-counted-bird-outline="4"]');
        if (!image || !cardinal) throw new Error('Missing counted frame or bird outline');
        return { image: image.getBoundingClientRect().toJSON(), cardinal: cardinal.getBoundingClientRect().toJSON() };
    });
    expect(Math.abs(image.width / image.height - 3840 / 2160)).toBeLessThan(0.01);
    expect((cardinal.x - image.x) / image.width).toBeCloseTo(1454 / 3840, 2);
    expect((cardinal.y - image.y) / image.height).toBeCloseTo(1265 / 2160, 2);
    expect(cardinal.width / image.width).toBeCloseTo((1642 - 1454) / 3840, 2);

    // The counted total is the stored count; the Unknown bird stays Unknown with its guess stated.
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await expect(page.locator('[data-counted-birds-summary]')).toContainText('Unknown: 1');
    const unknownRow = page.locator('[data-counted-bird-row="3"] [data-counted-bird-select]');
    await expect(unknownRow).toContainText('Unknown bird');
    await expect(unknownRow).toContainText('Too uncertain to name');
    await unknownRow.click();
    await expect(page.locator('[data-counted-bird-details]')).toContainText('Best guess Poecile hudsonicus at 27%, too low to name.');
    await expect(page.locator('[data-counted-bird-outline="3"]')).toHaveAttribute('data-lit', 'true');
    await expect(page.locator('[data-counted-bird-tag]')).toHaveText('Unknown bird');
    await expect(unknownRow).toHaveAttribute('aria-expanded', 'true');
    await page.screenshot({ path: testInfo.outputPath('cardinal-selected.png'), fullPage: true });
});

test('keyboard focus previews a bird on the scene and Enter selects it', async ({ page, browserName }) => {
    await open(page, 'case=cardinal');
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(2);
    await page.locator('[data-counted-bird-row="4"] [data-counted-bird-select]').focus();
    await expect(page.locator('[data-counted-bird-outline="4"]')).toHaveAttribute('data-lit', 'true');
    await expect(page.locator('[data-counted-bird-outline="3"]')).toHaveAttribute('data-lit', 'false');
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-counted-bird-row="4"] [data-counted-bird-details]')).toBeVisible();
    // Safari moves between buttons with Option+Tab.
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    await expect(page.locator('[data-counted-bird-correct]')).toBeFocused();
});

test('a large set states its total, expands to every bird, and keeps repeated species apart', async ({ page }, testInfo) => {
    await open(page, 'case=many');
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('58');
    await expect(page.locator('[data-counted-birds-summary]')).toContainText('Excluded: 2');
    await expect(page.locator('[data-counted-bird-row]')).toHaveCount(6);
    const expand = page.locator('[data-counted-birds-expand]');
    await expect(expand).toHaveText('Show all 60 birds');
    await expect(expand).toHaveAttribute('aria-expanded', 'false');
    await expand.click();
    await expect(page.locator('[data-counted-bird-row]')).toHaveCount(60);
    await expect(page.locator('[data-counted-birds-excluded-heading]')).toHaveText('Excluded, not counted');
    await expect(page.locator('[data-counted-bird-row][data-excluded="true"]')).toHaveCount(2);
    // Every counted bird is outlined, whatever is expanded; excluded birds only when looked at.
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(58);

    const finches = page.locator('[data-counted-bird-select]', { hasText: 'House Finch' });
    await expect(finches).toHaveCount(3);
    await expect(finches.nth(0)).toContainText('1 of 3 from the left');
    await expect(finches.nth(2)).toContainText('3 of 3 from the left');

    const late = page.locator('[data-counted-bird-row="45"] [data-counted-bird-select]');
    await late.scrollIntoViewIfNeeded();
    await late.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-counted-bird-outline="45"]')).toHaveAttribute('data-lit', 'true');
    await page.screenshot({ path: testInfo.outputPath('many-expanded.png'), fullPage: true });
});

test('a resized image cannot carry frame-pixel boxes, so outlines are withheld and the list stays', async ({ page }) => {
    await open(page, 'case=resized');
    await expect(page.locator('[data-counted-birds-unavailable="geometry"]')).toBeVisible();
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(0);
    // Keep the frame's reserved space and honest geometry warning, with no boxes.
    await expect(page.locator('[data-counted-birds-scene]')).toHaveCount(1);
    await expect(page.locator('[data-counted-bird-row]')).toHaveCount(2);
    await expect(page.locator('[data-counted-bird-crop="placeholder"]')).toHaveCount(2);
});

test('a thumbnail-only scene is never fetched for geometry', async ({ page }) => {
    const fixture = await open(page, 'case=thumbnail');
    await expect(page.locator('[data-counted-birds-unavailable="thumbnail_only"]')).toBeVisible();
    await expect(page.locator('[data-counted-bird-row]')).toHaveCount(2);
    expect(fixture.requests.filter(request => request.includes('thumb'))).toEqual([]);
});

test('a scene that fails to load says so and keeps the birds', async ({ page }) => {
    await open(page, 'case=missing');
    await expect(page.locator('[data-counted-birds-unavailable="load_failed"]')).toBeVisible();
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(0);
    await expect(page.locator('[data-counted-bird-row]')).toHaveCount(2);
});

test('a late load of the previous scene cannot size the recounted scene', async ({ page }) => {
    let release: () => void = () => undefined;
    const fixture: Fixture = { requests: [], slowScene: new Promise<void>(resolve => { release = resolve; }) };
    await open(page, 'case=late', fixture, 'domcontentloaded');
    await expect.poll(() => fixture.requests).toContain('GET /api/fixture/scene-slow.svg');
    await page.locator('[data-fixture-recount]').click();
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(1);
    release();
    await page.waitForTimeout(150);
    const image = await page.locator('[data-counted-birds-frame] img').boundingBox();
    const box = await page.locator('[data-counted-bird-outline="4"]').boundingBox();
    expect(Math.abs(image!.width / image!.height - 1920 / 1080)).toBeLessThan(0.01);
    expect((box!.x - image!.x) / image!.width).toBeCloseTo(400 / 1920, 2);
    await expect(page.locator('[data-counted-birds-provenance]')).toContainText('frame 200');
});

test('correcting and excluding a bird updates its stable row and the count', async ({ page }) => {
    await open(page, 'case=cardinal', {
        requests: [],
        patch: async (route, change, birdId) => { await route.fulfill({ json: cardinalBird(birdId, change) }); }
    });
    await page.locator('[data-counted-bird-row="3"] [data-counted-bird-select]').click();
    await page.locator('[data-counted-bird-correct]').click();
    await page.getByRole('textbox', { name: 'Species for Unknown bird' }).fill('Northern');
    await page.getByRole('button', { name: 'Northern Cardinal' }).click();
    await page.getByRole('button', { name: 'Save species' }).click();
    await expect(page.locator('[data-counted-bird-row="3"] [data-counted-bird-select]')).toContainText('Your correction');
    await expect(page.locator('[data-counted-birds-summary]')).toContainText('Unknown: 0');

    // Saving removes the form; focus returns to the bird's own controls rather than the page.
    await expect(page.locator('[data-counted-bird-row="3"] [data-counted-bird-correct]')).toBeFocused();

    await page.getByRole('button', { name: 'Exclude from the count' }).click();
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    await expect(page.locator('[data-counted-bird-row="3"]')).toHaveAttribute('data-excluded', 'true');
    // The row moved to the excluded group; focus stays on its action so Escape still reaches the dialog.
    await expect(page.getByRole('button', { name: 'Count this bird again' })).toBeFocused();
    await expect(page.locator('[data-counted-birds-excluded-heading]')).toBeVisible();
    await page.getByRole('button', { name: 'Count this bird again' }).click();
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
});

test('an edit answered after the birds were reread is not applied and asks for a reread', async ({ page }) => {
    let release: () => void = () => undefined;
    const gate = new Promise<void>(resolve => { release = resolve; });
    await open(page, 'case=cardinal', {
        requests: [],
        patch: async (route, change, birdId) => { await gate; await route.fulfill({ json: cardinalBird(birdId, change) }); }
    });
    await page.locator('[data-counted-bird-row="4"] [data-counted-bird-select]').click();
    await page.getByRole('button', { name: 'Exclude from the count' }).click();
    await page.locator('[data-fixture-recount]').click();
    release();
    await expect(page.locator('[data-fixture-stale]')).toHaveText('1');
    await expect(page.locator('[data-fixture-changed]')).toHaveText('0');
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    await expect(page.locator('[data-counted-bird-row="4"]')).toHaveAttribute('data-excluded', 'false');
});

test('not counted, loading and failed states are worded, never zero', async ({ page }) => {
    await open(page, 'case=empty');
    await expect(page.locator('[data-counted-birds-state="not-counted"]')).toContainText('not the same as none');
    await expect(page.locator('[data-counted-birds-total]')).toHaveCount(0);
    // While the first read is pending nothing is claimed, and nothing appears only to vanish.
    await page.goto('/browser-tests/counted-birds.html?case=empty&state=loading');
    await expect(page.locator('[data-fixture-stale]')).toBeVisible();
    await expect(page.locator('[data-counted-birds]')).toHaveCount(0);
    await page.goto('/browser-tests/counted-birds.html?case=cardinal&state=error');
    await expect(page.locator('[data-counted-birds-state="error"]')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Retry' })).toBeVisible();
});

test('the field log names the busiest capture, never sums frames, and opens it', async ({ page }) => {
    await open(page, 'case=fieldlog');
    const markers = page.locator('[data-field-log-birds]');
    await expect(markers).toHaveCount(2);
    await expect(markers.nth(0)).toHaveText('3 birds in one capture, 1 unknown');
    await expect(markers.nth(0)).toHaveAccessibleName('3 birds in one capture, 1 unknown, open that capture');
    await expect(markers.nth(1)).toHaveText('No birds counted, 1 excluded');
    // Captures and birds are two numbers, stated apart, so a capture is never read as a bird.
    await expect(page.locator('[data-field-log-captures]')).toHaveText('2 captures');
    await expect(page.locator('[data-field-log-footer]').first()).not.toContainText('2 captures');
    await markers.nth(0).click();
    await expect(page.locator('[data-fixture-opened]')).toHaveText('visit-a-2');
});

for (const scenario of ['cardinal', 'many', 'fieldlog']) {
    test(`${scenario}: targets are at least 44px, distinct and do not overflow at 320px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 320, height: 800 });
        await open(page, `case=${scenario}`, {
            requests: [],
            patch: async (route, change, birdId) => { await route.fulfill({ json: cardinalBird(birdId, change) }); }
        });
        await targetsAreUsable(page);
        if (scenario !== 'fieldlog') {
            await page.locator('[data-counted-bird-select]').first().click();
            await page.locator('[data-counted-bird-correct]').click();
            await page.locator('[data-counted-bird-details] input').fill('Northern');
            await targetsAreUsable(page);
        }
        await page.screenshot({ path: testInfo.outputPath(`${scenario}-320.png`), fullPage: true });
    });
}

test('reduced motion and 200% text keep the list usable', async ({ page }, testInfo) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.setViewportSize({ width: 320, height: 800 });
    await open(page, 'case=cardinal');
    await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
    await page.locator('[data-counted-bird-select]').first().click();
    await targetsAreUsable(page);
    await page.screenshot({ path: testInfo.outputPath('cardinal-320-200pct.png'), fullPage: true });
});

for (const language of ['de', 'fr', 'ru']) {
    test(`${language}: long translated labels fit at 320px with 200% text`, async ({ page }, testInfo) => {
        await page.addInitScript((value) => localStorage.setItem('preferred-language', value), language);
        await page.setViewportSize({ width: 320, height: 800 });
        await open(page, 'case=many', {
            requests: [],
            patch: async (route, change, birdId) => { await route.fulfill({ json: cardinalBird(birdId, change) }); }
        });
        await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
        await expect(page.locator('[data-counted-birds-expand]')).not.toHaveText('Show all 60 birds');
        // The crop is cut for a 44px edge, so it must stay 44px whatever the text size.
        const crop = await page.locator('[data-counted-bird-crop]').first().boundingBox();
        expect([Math.round(crop!.width), Math.round(crop!.height)]).toEqual([44, 44]);
        // Names wrap at words, never one letter per line.
        const name = await page.locator('[data-counted-bird-select] span.text-sm').first().boundingBox();
        expect(name!.width).toBeGreaterThan(90);
        await page.locator('[data-counted-bird-select]').first().click();
        await page.locator('[data-counted-bird-correct]').click();
        await targetsAreUsable(page);
        await page.screenshot({ path: testInfo.outputPath(`many-${language}-320-200pct.png`), fullPage: true });
    });
}
