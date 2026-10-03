import { test, expect, type Page } from '@playwright/test';

function capture(id: string, overrides: Record<string, unknown> = {}) {
    return { frigate_event: id, display_name: 'Turdus merula', scientific_name: 'Turdus merula', common_name: 'Eurasian Blackbird', camera_name: 'birdcam', detection_time: '2026-10-02T10:42:21Z', score: 0.95, has_clip: true, ...overrides };
}
async function prepare(page: Page, query = '') {
    const requests: URL[] = [];
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        if (url.pathname.endsWith('/captures')) {
            requests.push(url);
            const offset = Number(url.searchParams.get('offset'));
            const window = url.searchParams.get('start_date');
            const prefix = window === '2026-10-03' ? 'next' : 'original';
            return route.fulfill({ json: { captures: Array.from({ length: offset ? 1 : 20 }, (_, index) => capture(`${prefix}-${offset + index}`, {
                detection_time: new Date(Date.parse('2026-10-02T10:42:21Z') + (offset + index) * 7000).toISOString(),
                ...(offset + index === 0 ? { frigate_event: 'first' } : {}),
                ...(offset + index === 3 ? { bird_summary: { counted: 3, unknown: 0, excluded: 0, species: [], hint_only: false } } : {})
            })), total: 21 } });
        }
        if (url.pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#166534"/></svg>' });
        return route.fulfill({ json: {} });
    });
    await page.goto(`/browser-tests/visits.html${query}`);
    await expect(toggle(page)).toContainText('21 captures');
    return { requests, errors };
}
function toggle(page: Page) {
    return page.locator('[data-visit-captures="first"] [data-visit-captures-toggle]');
}
const openCapture = /^Open Eurasian Blackbird capture at /;

test('floating captures leave the next card in place and dismiss with Escape or outside click', async ({ page }) => {
    const { errors } = await prepare(page, '?floating=1');
    const next = page.locator('[data-fixture-single]');
    const before = await next.boundingBox();
    await toggle(page).focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-visit-capture="first"]')).toBeVisible();
    const after = await next.boundingBox();
    expect(after?.y).toBe(before?.y);
    await expect(page.locator('[data-visit-capture="first"]').getByText('Eurasian Blackbird', { exact: true })).toBeVisible();
    await expect(page.locator('[data-visit-capture="first"]').getByText('Turdus merula', { exact: true })).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false');
    await expect(toggle(page)).toBeFocused();
    await toggle(page).click();
    await page.getByRole('heading').click();
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false');
    expect(errors).toEqual([]);
});

test('a thumbnail preview paints above its floating capture panel', async ({ page, isMobile }) => {
    test.skip(isMobile, 'Touch opens the exact record without a hover preview');
    await prepare(page, '?floating=1');
    await toggle(page).click();
    await page.locator('[data-visit-capture="first"] [data-detection-preview] button').hover();
    const preview = page.locator('[data-detection-preview-panel]');
    await expect(preview).toBeVisible();
    expect(await preview.evaluate(element => {
        const rect = element.getBoundingClientRect();
        return element.contains(document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2));
    })).toBe(true);
});

test('scrolling a floating capture control out of view closes its panel', async ({ page }) => {
    await prepare(page, '?floating=1');
    await page.locator('main').evaluate(element => { element.style.minHeight = '3000px'; });
    await toggle(page).click();
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'true');
    await page.evaluate(() => scrollTo(0, 800));
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('[data-visit-captures-floating]')).toBeHidden();
});

for (const width of [320, 390, 1280]) {
    test(`floating captures fit ${width}px and close after opening an exact capture`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 700 });
        const { errors } = await prepare(page, '?floating=1&theme=dark');
        await toggle(page).click();
        const panel = page.locator('[data-visit-captures-floating]');
        await expect(panel).toBeVisible();
        const bounds = await panel.boundingBox();
        expect(bounds?.x ?? -1).toBeGreaterThanOrEqual(0);
        expect((bounds?.x ?? 0) + (bounds?.width ?? 0)).toBeLessThanOrEqual(width);
        expect(bounds?.y ?? -1).toBeGreaterThanOrEqual(0);
        expect((bounds?.y ?? 0) + (bounds?.height ?? 0)).toBeLessThanOrEqual(700);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath(`floating-captures-${width}.png`) });
        await panel.locator('[data-visit-capture="first"] > button').click();
        await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('first');
        await expect(panel).toBeHidden();
        await toggle(page).click();
        await panel.getByRole('button', { name: 'Close', exact: true }).click();
        await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false');
        expect(errors).toEqual([]);
    });
}

test('visit captures load on keyboard expansion, paginate, and open exact record or clip', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    expect(requests).toHaveLength(0);
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false');
    await toggle(page).focus();
    await page.keyboard.press('Enter');
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'true');
    await expect(toggle(page)).toBeFocused();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(20);
    // The list does not repeat the visit; it tells captures apart by the second.
    await expect(page.locator('[data-visit-capture]').nth(1).locator('time')).toHaveText(/\d{2}:\d{2}:\d{2}/);
    await expect(page.locator('[data-visit-capture="first"]')).toContainText('Visit photo');
    await expect(page.locator('[data-visit-capture="original-3"]')).toContainText('3 birds');
    await expect(page.getByText('20 of 21 captures shown')).toBeVisible();
    await page.getByRole('button', { name: openCapture }).nth(7).click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('original-7');
    await page.getByRole('button', { name: /Play/ }).first().click();
    await expect(page.getByRole('status', { name: 'Played record' })).toHaveText('first');
    await page.getByRole('button', { name: 'Load more captures' }).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(21);
    await expect(page.getByRole('button', { name: 'Load more captures' })).toHaveCount(0);
    expect(requests.map(url => url.searchParams.get('offset'))).toEqual(['0', '20']);
    expect(errors).toEqual([]);
});

test('closing and reopening a visit reuses the captures it already read', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    await toggle(page).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(20);
    await toggle(page).click();
    await expect(toggle(page)).toHaveAttribute('aria-expanded', 'false');
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(0);
    await toggle(page).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(20);
    expect(requests).toHaveLength(1);
    expect(errors).toEqual([]);
});

test('a single-capture visit stays a clean record with no capture list or read', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    await expect(page.locator('[data-fixture-single]')).toBeVisible();
    await expect(page.locator('[data-visit-captures="single"]')).toHaveCount(0);
    await expect(page.locator('[data-fixture-single] button')).toHaveCount(0);
    expect(requests.filter(url => url.pathname.includes('/single/'))).toHaveLength(0);
    expect(errors).toEqual([]);
});

test('retained expanded timeline reloads when its window and membership change', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    await toggle(page).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(20);
    await page.getByRole('button', { name: 'Change window' }).click();
    await expect.poll(() => requests.at(-1)?.searchParams.get('start_date')).toBe('2026-10-03');
    await page.getByRole('button', { name: openCapture }).nth(1).click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('next-1');
    const reads = requests.length;
    await page.getByRole('button', { name: 'New capture', exact: true }).click();
    await expect(toggle(page)).toContainText('22 captures');
    await expect.poll(() => requests.length).toBe(reads + 1);
    expect(requests.at(-1)?.searchParams.get('offset')).toBe('0');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    expect(errors).toEqual([]);
});

test('a delayed earlier window cannot overwrite the expanded current window', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    let release: () => void = () => undefined;
    const held = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/visits/first/captures?**', async route => {
        const url = new URL(route.request().url());
        requests.push(url);
        if (url.searchParams.get('start_date') === '2026-10-02') {
            await held;
            return route.fulfill({ json: { captures: [capture('withdrawn')], total: 1 } }).catch(() => undefined);
        }
        return route.fulfill({ json: { captures: [capture('current')], total: 1 } });
    });
    await toggle(page).click();
    await expect.poll(() => requests.length).toBe(1);
    await page.getByRole('button', { name: 'Change window' }).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(1);
    release();
    await page.getByRole('button', { name: openCapture }).click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('current');
    expect(errors).toEqual([]);
});

test('changing owner access replaces the expanded private projection and says so', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    await toggle(page).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(20);
    await page.route('**/api/visits/first/captures?**', route => {
        requests.push(new URL(route.request().url()));
        return route.fulfill({ json: { captures: [], total: 0 } });
    });
    await page.getByRole('button', { name: 'Guest access' }).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(0);
    await expect(page.getByText('No captures from this visit are visible in this view.')).toBeVisible();
    await expect.poll(() => requests.length).toBe(2);
    expect(errors).toEqual([]);
});

test('a failed read says so in words and retries in place', async ({ page }) => {
    const { errors } = await prepare(page);
    let fail = true;
    await page.route('**/api/visits/first/captures?**', route => fail
        ? route.fulfill({ status: 500, json: { detail: 'unavailable' } })
        : route.fulfill({ json: { captures: [capture('recovered')], total: 1 } }));
    await toggle(page).click();
    await expect(page.getByRole('alert')).toContainText('Could not load the captures. Try again.');
    fail = false;
    await page.getByRole('alert').getByRole('button', { name: 'Retry' }).click();
    await expect(page.getByRole('button', { name: openCapture })).toHaveCount(1);
    expect(errors).toEqual([]);
});

for (const theme of ['light', 'dark']) {
    test(`inline captures fit a 320px phone with usable targets (${theme})`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 320, height: 900 });
        const { errors } = await prepare(page, `?layout=inline&theme=${theme}`);
        await toggle(page).click();
        await expect(page.getByRole('button', { name: openCapture })).toHaveCount(20);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const panel = page.locator('[data-visit-captures="first"]');
        for (const control of await panel.locator('button:visible').all()) {
            const box = await control.boundingBox();
            expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
        }
        // Times are never clipped by the score and clip controls beside them.
        for (const time of await panel.locator('time').all()) {
            expect(await time.evaluate(element => element.scrollWidth <= element.clientWidth)).toBe(true);
        }
        await page.screenshot({ path: testInfo.outputPath(`visit-captures-inline-${theme}.png`), fullPage: true });
        expect(errors).toEqual([]);
    });
}


test('a settled owner recount refreshes expanded evidence without changing visit membership', async ({ page }) => {
    const { errors } = await prepare(page);
    let counted = 2;
    let requests = 0;
    await page.route('**/api/visits/first/captures?**', route => {
        requests += 1;
        return route.fulfill({ json: { captures: [capture('first', {
            bird_summary: { counted, unknown: 0, excluded: 0, species: [], hint_only: false }
        })], total: 21 } });
    });
    await toggle(page).click();
    await expect(page.locator('[data-visit-capture="first"]')).toContainText('2 birds');
    counted = 3;
    await page.getByRole('button', { name: 'Recount settled' }).click();
    await expect(page.locator('[data-visit-capture="first"]')).toContainText('3 birds');
    expect(requests).toBe(2);
    expect(errors).toEqual([]);
});
