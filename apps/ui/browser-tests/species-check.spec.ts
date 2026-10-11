import { test, expect, type Page } from '@playwright/test';

// Set UI_SHOTS to a directory to keep review screenshots of the sheet.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

const COLOURS = ['#8a6f4e', '#5b6b3a', '#7d7f86', '#a08560'];

function detection(event: string, species: string, scientific: string, time: string, score: number) {
    return {
        id: 1, detection_time: time, detection_index: 1, score, display_name: species, category_name: scientific, frigate_event: event,
        observation_source: 'frigate', camera_name: 'birdcam', is_hidden: false, is_favorite: false, manual_tagged: false, audio_confirmed: false,
        scientific_name: scientific, common_name: species, has_clip: false, has_snapshot: true, has_frigate_event: true
    };
}

function visit(event: string, species: string, scientific: string, time: string, score: number, captures = 1) {
    const capture = detection(event, species, scientific, time, score);
    return { visit_id: event, start_time: time, end_time: time, capture_count: captures, best_score: score, needs_review: false, audio_confirmed: false, representative: capture, latest: capture, peak_capture: capture };
}

const VISITS: Record<string, ReturnType<typeof visit>[]> = {
    'Brown-headed Cowbird': [
        visit('cowbird-1', 'Brown-headed Cowbird', 'Molothrus ater', '2026-09-21T12:44:20Z', 0.73, 2),
        visit('cowbird-2', 'Brown-headed Cowbird', 'Molothrus ater', '2026-09-19T08:10:00Z', 0.68),
        visit('cowbird-3', 'Brown-headed Cowbird', 'Molothrus ater', '2026-09-12T16:02:00Z', 0.61)
    ],
    'Eastern Gray Squirrel': [
        // More captures than one page of the captures route holds.
        visit('squirrel-1', 'Eastern Gray Squirrel', 'Sciurus carolinensis', '2026-10-01T09:00:00Z', 0.93, 55),
        visit('squirrel-2', 'Eastern Gray Squirrel', 'Sciurus carolinensis', '2026-09-28T09:30:00Z', 0.88)
    ],
    'Plateau Striped Whiptail': [visit('whiptail-1', 'Plateau Striped Whiptail', 'Aspidoscelis velox', '2026-09-19T12:18:00Z', 0.66)]
};

const feederSpecies = [
    ['Dunnock', 'Prunella modularis'], ['European Robin', 'Erithacus rubecula'], ['Great Tit', 'Parus major'],
    ['Eurasian Blackbird', 'Turdus merula'], ['Blue Tit', 'Cyanistes caeruleus']
].map(([common, scientific]) => ({ id: scientific, display_name: common, common_name: common, scientific_name: scientific }));

interface Calls { renamed: { event_ids: string[]; display_name: string }[]; hidden: string[] }

async function serve(page: Page): Promise<Calls> {
    const calls: Calls = { renamed: [], hidden: [] };
    await page.route('**/api/visits?**', async (route) => {
        const species = new URL(route.request().url()).searchParams.get('species') ?? '';
        const visits = VISITS[species] ?? [];
        await route.fulfill({ json: { visits, total: visits.length, gap_seconds: 60 } });
    });
    await page.route('**/api/visits/*/captures**', async (route) => {
        const url = new URL(route.request().url());
        const id = decodeURIComponent(url.pathname.split('/')[3]);
        const limit = Number(url.searchParams.get('limit') ?? 20);
        const offset = Number(url.searchParams.get('offset') ?? 0);
        // The route's own bounds: a larger page is refused, as the server refuses it.
        if (limit > 50) {
            await route.fulfill({ status: 422, json: { detail: [{ msg: 'Input should be less than or equal to 50' }] } });
            return;
        }
        const owner = Object.values(VISITS).flat().find((entry) => entry.visit_id === id);
        const all = Array.from({ length: owner?.capture_count ?? 1 }, (_, index) =>
            detection(index === 0 ? id : `${id}-${index}`, owner?.representative.display_name ?? '', owner?.representative.scientific_name ?? '', '2026-09-21T12:44:20Z', 0.7)
        );
        await route.fulfill({ json: { captures: all.slice(offset, offset + limit), total: all.length } });
    });
    await page.route('**/api/frigate/*/snapshot/candidates', async (route) => {
        const event = new URL(route.request().url()).pathname.split('/')[3];
        const cowbird = event.startsWith('cowbird');
        await route.fulfill({
            json: {
                event_id: event,
                candidates: [
                    { candidate_id: 'scene', source_mode: 'full_frame', classifier_label: null, classifier_score: null, clip_variant: 'event', frame_index: 0, ranking_score: 0.9, selected: false, thumbnail_url: `/media/${event}-scene.jpg`, image_url: `/media/${event}-scene.jpg` },
                    { candidate_id: 'crop', source_mode: 'model_crop', classifier_label: cowbird && event !== 'cowbird-3' ? 'Prunella modularis' : null, classifier_score: 0.4, clip_variant: 'event', frame_index: 0, ranking_score: 0.6, selected: false, thumbnail_url: `/media/${event}.jpg`, image_url: `/media/${event}.jpg` }
                ]
            }
        });
    });
    await page.route('**/media/*.jpg', async (route) => {
        const name = new URL(route.request().url()).pathname;
        const shots = environment.CHECK_CROPS;
        const fill = COLOURS[name.length % COLOURS.length];
        if (shots) {
            // @ts-expect-error The UI has no Node type package; the fixture server runs in Node.
            const { readFileSync } = await import('node:fs');
            const file = name.includes('squirrel') ? 'squirrel' : name.includes('whiptail') ? 'whiptail' : 'cowbird';
            await route.fulfill({ contentType: 'image/jpeg', body: readFileSync(`${shots}/${file}.jpg`) });
            return;
        }
        await route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="10" height="10" fill="${fill}"/><circle cx="5" cy="5" r="2.5" fill="#3b2f25"/></svg>` });
    });
    await page.route('**/api/taxonomy/lineage**', async (route) => {
        const name = new URL(route.request().url()).searchParams.get('scientific_name');
        if (name === 'Molothrus ater') {
            await route.fulfill({ json: { lineage: [{ rank: 'class', scientific_name: 'Aves' }, { rank: 'species', scientific_name: 'Molothrus ater' }] } });
            return;
        }
        await route.fulfill({ status: 404, json: { detail: 'Not in the catalogue' } });
    });
    await page.route('**/api/species/search**', async (route) => {
        const term = (new URL(route.request().url()).searchParams.get('q') ?? '').toLowerCase();
        const pool = [...feederSpecies, { id: 'Molothrus aeneus', display_name: 'Bronzed Cowbird', common_name: 'Bronzed Cowbird', scientific_name: 'Molothrus aeneus' }];
        await route.fulfill({ json: term ? pool.filter((entry) => entry.display_name.toLowerCase().includes(term)) : feederSpecies });
    });
    await page.route('**/api/events/bulk/manual-tag', async (route) => {
        const body = route.request().postDataJSON() as Calls['renamed'][number];
        calls.renamed.push(body);
        await route.fulfill({ json: { status: 'updated', requested_count: body.event_ids.length, updated_count: body.event_ids.length, unchanged_count: 0, missing_count: 0, failed_count: 0, updated_event_ids: body.event_ids, unchanged_event_ids: [], missing_event_ids: [], failed_event_ids: [], new_species: body.display_name } });
    });
    await page.route('**/api/events/*/hide', async (route) => {
        const id = decodeURIComponent(new URL(route.request().url()).pathname.split('/')[3]);
        calls.hidden.push(id);
        await route.fulfill({ json: { status: 'ok', event_id: id, is_hidden: true } });
    });
    return calls;
}

async function shot(page: Page, name: string): Promise<void> {
    if (environment.UI_SHOTS) await page.screenshot({ path: `${environment.UI_SHOTS}/${name}.png` });
}

test('the suggestion renames every capture of the selected visits in one tap', async ({ page }) => {
    const calls = await serve(page);
    await page.goto('/browser-tests/species-check.html');
    const sheet = page.getByRole('dialog', { name: 'Brown-headed Cowbird' });
    await expect(sheet.getByText('3 visits, all from the camera alone.')).toBeVisible();
    await expect(sheet.locator('[data-species-check-visit]')).toHaveCount(3);
    // The crop, never the scene.
    await expect(sheet.locator('[data-species-check-visit] img').first()).toHaveAttribute('src', /cowbird-1\.jpg/);
    const primary = sheet.locator('[data-species-check-primary]');
    await expect(primary).toContainText('Dunnock');
    await expect(primary).toContainText('Another crop of 2 of these visits reads Dunnock.');
    await expect(primary).toContainText('Rename 3 visits');
    await shot(page, `check-cowbird-${page.viewportSize()?.width}`);

    // Leaving one out narrows the rename.
    await sheet.locator('[data-species-check-visit]').nth(2).click();
    await expect(primary).toContainText('Rename 2 visits');
    await primary.click();
    await expect.poll(() => calls.renamed).toEqual([{ event_ids: ['cowbird-1', 'cowbird-1-1', 'cowbird-2'], display_name: 'Prunella modularis' }]);
    await expect(page.getByText('2 visits are now Dunnock.')).toBeVisible();
    await expect(page.locator('[data-check-changes]')).toHaveText('1');
    await expect(page.getByRole('dialog', { name: 'Eastern Gray Squirrel' })).toBeVisible();
});

test('a confident camera on a mammal is confirmed, an unsure one on a lizard is hidden', async ({ page }) => {
    const calls = await serve(page);
    await page.goto('/browser-tests/species-check.html');
    await page.getByRole('dialog', { name: 'Brown-headed Cowbird' }).getByRole('button', { name: 'Skip for now' }).click();

    const squirrel = page.getByRole('dialog', { name: 'Eastern Gray Squirrel' });
    await expect(squirrel.getByText('Birders report birds, so the nearby check cannot speak for this one.')).toBeVisible();
    await expect(squirrel.locator('[data-species-check-primary]')).toContainText('It really is a Eastern Gray Squirrel');
    await page.keyboard.press('1');
    // Every one of the 55 captures moves with its visit, read a page at a time.
    await expect.poll(() => calls.renamed.length).toBe(1);
    expect(calls.renamed[0].display_name).toBe('Eastern Gray Squirrel');
    expect(calls.renamed[0].event_ids).toHaveLength(56);
    expect(calls.renamed[0].event_ids).toContain('squirrel-1-54');
    expect(page.getByText('Input should be less than or equal to 50')).toHaveCount(0);

    const whiptail = page.getByRole('dialog', { name: 'Plateau Striped Whiptail' });
    await expect(whiptail.locator('[data-species-check-visit]').first()).toBeInViewport();
    await expect(whiptail.locator('[data-species-check-primary]')).toContainText('Not a bird');
    await shot(page, `check-whiptail-${page.viewportSize()?.width}`);
    await whiptail.locator('[data-species-check-primary]').click();
    await expect.poll(() => calls.hidden).toEqual(['whiptail-1']);

    // The skipped species comes back last.
    await expect(page.getByRole('dialog', { name: 'Brown-headed Cowbird' })).toBeVisible();
});

test('another species takes a second, deliberate tap', async ({ page }) => {
    const calls = await serve(page);
    await page.goto('/browser-tests/species-check.html');
    const sheet = page.getByRole('dialog', { name: 'Brown-headed Cowbird' });
    await expect(sheet.locator('[data-species-check-visit]')).toHaveCount(3);
    await sheet.getByRole('searchbox', { name: 'Search all species' }).fill('bronzed');
    await sheet.getByRole('button', { name: /Bronzed Cowbird/ }).click();
    expect(calls.renamed).toEqual([]);
    await sheet.locator('[data-species-check-rename]').click();
    await expect.poll(() => calls.renamed.map((call) => call.display_name)).toEqual(['Molothrus aeneus']);
});

test('the last answer ends on a summary', async ({ page }) => {
    await serve(page);
    await page.goto('/browser-tests/species-check.html');
    for (const name of ['Brown-headed Cowbird', 'Eastern Gray Squirrel', 'Plateau Striped Whiptail']) {
        const sheet = page.getByRole('dialog', { name });
        await expect(sheet.locator('[data-species-check-visit]').first()).toBeVisible();
        await sheet.locator('[data-species-check-primary]').click();
    }
    await expect(page.getByRole('dialog', { name: 'All checked' })).toContainText('3 species checked.');
    await page.getByRole('button', { name: 'Close', exact: true }).click();
    await expect(page.getByRole('dialog')).toHaveCount(0);
});

for (const width of [375, 1440]) {
    test(`fits a ${width}px screen without sideways scroll and with reachable answers`, async ({ page }) => {
        await page.setViewportSize({ width, height: width < 600 ? 812 : 900 });
        await serve(page);
        await page.goto('/browser-tests/species-check.html');
        const sheet = page.getByRole('dialog', { name: 'Brown-headed Cowbird' });
        await expect(sheet.locator('[data-species-check-visit]')).toHaveCount(3);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        for (const button of await sheet.getByRole('button').all()) {
            if (!(await button.isVisible())) continue;
            const box = await button.boundingBox();
            expect(box?.height ?? 0, await button.innerText()).toBeGreaterThanOrEqual(44);
        }
        const primary = sheet.locator('[data-species-check-primary]');
        await primary.scrollIntoViewIfNeeded();
        await expect(primary).toBeInViewport();
        const box = await primary.boundingBox();
        expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual(width);
    });
}
