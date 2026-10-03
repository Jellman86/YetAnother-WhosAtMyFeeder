import { test, expect, type Page } from '@playwright/test';

function capture(id: string) {
    return { frigate_event: id, display_name: 'Turdus merula', scientific_name: 'Turdus merula', common_name: 'Eurasian Blackbird', camera_name: 'birdcam', detection_time: '2026-10-02T10:42:21Z', score: 0.95, has_clip: true };
}
async function prepare(page: Page) {
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
            return route.fulfill({ json: { captures: Array.from({ length: offset ? 1 : 20 }, (_, index) => capture(`${prefix}-${offset + index}`)), total: 21 } });
        }
        if (url.pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="100"><rect width="100" height="100" fill="#166534"/></svg>' });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/visits.html');
    await expect(page.locator('summary')).toContainText('21 captures');
    return { requests, errors };
}

test('visit captures load on keyboard expansion, paginate, and open exact record or clip', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    expect(requests).toHaveLength(0);
    await page.locator('summary').focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: /^Open Eurasian Blackbird/ })).toHaveCount(20);
    await page.getByRole('button', { name: /^Open Eurasian Blackbird/ }).nth(7).click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('original-7');
    await page.getByRole('button', { name: /Play/ }).first().click();
    await expect(page.getByRole('status', { name: 'Played record' })).toHaveText('original-0');
    await page.getByRole('button', { name: 'Load more captures' }).click();
    await expect(page.getByRole('button', { name: /^Open Eurasian Blackbird/ })).toHaveCount(21);
    expect(requests.map(url => url.searchParams.get('offset'))).toEqual(['0', '20']);
    expect(errors).toEqual([]);
});

test('retained expanded timeline reloads when its window and membership change', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    await page.locator('summary').click();
    await expect(page.getByRole('button', { name: /^Open Eurasian Blackbird/ })).toHaveCount(20);
    await page.getByRole('button', { name: 'Change window' }).click();
    await expect.poll(() => requests.at(-1)?.searchParams.get('start_date')).toBe('2026-10-03');
    await page.getByRole('button', { name: /^Open Eurasian Blackbird/ }).first().click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('next-0');
    const reads = requests.length;
    await page.getByRole('button', { name: 'New capture', exact: true }).click();
    await expect(page.locator('summary')).toContainText('22 captures');
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
    await page.locator('summary').click();
    await expect.poll(() => requests.length).toBe(1);
    await page.getByRole('button', { name: 'Change window' }).click();
    await expect(page.getByRole('button', { name: /^Open Eurasian Blackbird/ })).toHaveCount(1);
    release();
    await page.getByRole('button', { name: /^Open Eurasian Blackbird/ }).click();
    await expect(page.getByRole('status', { name: 'Selected record' })).toHaveText('current');
    expect(errors).toEqual([]);
});

test('changing owner access replaces the expanded private projection', async ({ page }) => {
    const { requests, errors } = await prepare(page);
    await page.locator('summary').click();
    await expect(page.getByRole('button', { name: /^Open Eurasian Blackbird/ })).toHaveCount(20);
    await page.route('**/api/visits/first/captures?**', route => {
        requests.push(new URL(route.request().url()));
        return route.fulfill({ json: { captures: [], total: 0 } });
    });
    await page.getByRole('button', { name: 'Guest access' }).click();
    await expect(page.getByRole('button', { name: /^Open Eurasian Blackbird/ })).toHaveCount(0);
    await expect.poll(() => requests.length).toBe(2);
    expect(errors).toEqual([]);
});
