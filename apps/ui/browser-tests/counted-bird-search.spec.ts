import { test, expect, type Page } from '@playwright/test';

const dunnock = { id: 'Prunella modularis', display_name: 'Prunella modularis', common_name: 'Dunnock', scientific_name: 'Prunella modularis' };
const robin = { id: 'Erithacus rubecula', display_name: 'Erithacus rubecula', common_name: 'European Robin', scientific_name: 'Erithacus rubecula' };
const bird = { id: 694, bird_index: 0, candidate_id: 'crop', clip_variant: 'frigate_snapshot', frame_index: 0,
    crop_box: [873, 341, 1112, 480], detector_confidence: .509, species: 'Prunella modularis',
    common_name: 'Dunnock', scientific_name: 'Prunella modularis', classifier_label: 'Prunella modularis',
    classifier_score: .4519, identity_source: 'visit', identity_score: .9396, manual_species: false, is_hidden: false };

async function open(page: Page, surface: string, search?: (q: string) => Promise<{ status?: number; results: typeof dunnock[] }>) {
    const saves: unknown[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/species/search') {
            const q = url.searchParams.get('q') ?? '';
            const result = search ? await search(q) : { results: /robin|erithacus/i.test(q) ? [robin] : [dunnock] };
            return route.fulfill({ status: result.status ?? 200, json: result.results }).catch(() => undefined);
        }
        if (route.request().method() === 'PATCH' && url.pathname.endsWith('/birds/694')) {
            const change = route.request().postDataJSON(); saves.push(change);
            return route.fulfill({ json: { ...bird, ...change, manual_species: true, identity_source: 'manual' } });
        }
        if (url.pathname.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [bird] } });
        if (url.pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#334155"/></svg>' });
        return route.fulfill({ json: [] });
    });
    await page.goto(`/browser-tests/review-media.html?surface=${surface}&queue=dunnock`);
    const row = page.locator('[data-counted-bird-row="694"]');
    await row.locator('[data-counted-bird-select]').click();
    return { row, saves };
}

for (const surface of ['record', 'queue']) {
    for (const query of ['Dun', 'Dunnock', 'Prunella modularis']) {
        test(`${surface}: counted bird searches ${query} and saves its canonical identity`, async ({ page }) => {
            const { row, saves } = await open(page, surface);
            await row.locator('[data-counted-bird-correct]').click();
            await row.locator('input').fill(query);
            await expect(row.getByRole('button', { name: 'Save species' })).toBeDisabled();
            await row.getByRole('button', { name: 'Dunnock Prunella modularis', exact: true }).click();
            await row.getByRole('button', { name: 'Save species' }).click();
            await expect.poll(() => saves).toEqual([{ species: 'Prunella modularis' }]);
        });
    }

    test(`${surface}: accepted name and score remain distinct from crop evidence`, async ({ page }, testInfo) => {
        const { row } = await open(page, surface);
        await expect(row.locator('[data-counted-bird-select]')).toContainText('Dunnock');
        await expect(row.locator('[data-counted-bird-select]')).toContainText('94%');
        await expect(row.locator('[data-counted-bird-select]').getByText('94%', { exact: true }).filter({ visible: true }).first()).toBeVisible();
        await expect(row.locator('[data-counted-bird-select]').getByText('45%', { exact: true }).filter({ visible: true })).toHaveCount(0);
        await expect(row.locator('[data-counted-bird-details]')).toContainText('45%');
        await expect(row.locator('[data-counted-bird-details]')).toContainText('visit');
        await row.scrollIntoViewIfNeeded();
        await page.screenshot({ path: testInfo.outputPath('accepted-counted-bird.png') });
    });

    test(`${surface}: an owner-named visit does not lend its old model confidence`, async ({ page }) => {
        await open(page, surface);
        await page.route('**/snapshot/candidates', route => route.fulfill({ json: { candidates: [], birds: [{ ...bird, identity_score: null }] } }));
        await page.reload();
        const row = page.locator('[data-counted-bird-row="694"]');
        const heading = row.locator('[data-counted-bird-select]');
        await heading.click();
        await expect(heading).toContainText('Dunnock');
        await expect(heading).not.toContainText('%');
        await expect(row.locator('[data-counted-bird-details]')).toContainText('45%');
    });

    test(`${surface}: editing a chosen name requires a new complete choice`, async ({ page }) => {
        const { row, saves } = await open(page, surface);
        await row.locator('[data-counted-bird-correct]').click();
        const input = row.locator('input');
        await input.fill('Dunnock');
        await row.getByRole('button', { name: 'Dunnock Prunella modularis', exact: true }).click();
        await expect(row.getByRole('button', { name: 'Save species' })).toBeEnabled();
        await input.fill('Dun');
        await input.press('Enter');
        await expect(row.getByRole('button', { name: 'Save species' })).toBeDisabled();
        expect(saves).toEqual([]);
    });

    test(`${surface}: a late search cannot restore the previous species`, async ({ page }) => {
        let release: () => void = () => undefined;
        const held = new Promise<void>(resolve => { release = resolve; });
        const { row } = await open(page, surface, async q => {
            if (q === 'Dun') { await held; return { results: [dunnock] }; }
            return { results: [robin] };
        });
        await row.locator('[data-counted-bird-correct]').click();
        const pending = page.waitForRequest(r => new URL(r.url()).searchParams.get('q') === 'Dun');
        await row.locator('input').fill('Dun'); await pending;
        await row.locator('input').fill('Robin');
        await expect(row.getByRole('button', { name: 'European Robin Erithacus rubecula', exact: true })).toBeVisible();
        release();
        await page.waitForTimeout(250);
        await expect(row.getByRole('button', { name: 'Dunnock Prunella modularis', exact: true })).toHaveCount(0);
    });

    test(`${surface}: failed and empty searches keep saving disabled`, async ({ page }) => {
        const { row, saves } = await open(page, surface, async q => ({ status: q === 'fail' ? 503 : 200, results: [] }));
        await row.locator('[data-counted-bird-correct]').click();
        await row.locator('input').fill('fail');
        await expect(row).toContainText("Couldn't search species");
        await expect(row.getByRole('button', { name: 'Save species' })).toBeDisabled();
        await row.locator('input').fill('no such bird');
        await expect(row).toContainText('No species matches');
        expect(saves).toEqual([]);
    });

    test(`${surface}: keyboard selection works at 320px and enlarged text`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 320, height: 800 });
        const { row, saves } = await open(page, surface);
        await page.addStyleTag({ content: 'html { font-size: 200% !important; }' });
        await row.locator('[data-counted-bird-correct]').click();
        await row.locator('input').fill('Dunnock');
        const choice = row.getByRole('button', { name: 'Dunnock Prunella modularis', exact: true });
        await choice.focus(); await page.keyboard.press('Enter');
        const save = row.getByRole('button', { name: 'Save species' });
        await save.scrollIntoViewIfNeeded();
        const box = await save.boundingBox();
        expect(box?.width).toBeGreaterThanOrEqual(44);
        expect(box?.height).toBeGreaterThanOrEqual(44);
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.screenshot({ path: testInfo.outputPath('counted-search-320-large-text.png') });
        await save.focus(); await page.keyboard.press('Enter');
        await expect.poll(() => saves.length).toBe(1);
    });
}
