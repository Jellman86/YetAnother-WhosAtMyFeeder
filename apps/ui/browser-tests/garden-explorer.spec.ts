import { gardenVisitResponse } from './garden-visits-fixture';
import { test, expect, type Page } from '@playwright/test';

// Set EXPLORER_SHOTS to a directory to keep review screenshots outside the test output.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.EXPLORER_SHOTS;

const hoursAgo = (hours: number) => new Date(Date.now() - hours * 60 * 60 * 1000).toISOString();

function bird(id: string, at: string) {
    return {
        frigate_event: id, display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock',
        camera_name: 'birdcam', detection_time: at, score: 0.91, has_clip: false
    };
}

function capture(id: string, at: string, status: 'pending' | 'confirmed', name?: string, box?: [number, number, number, number]) {
    return {
        id: id.padEnd(32, '0'), camera: 'patio', frigate_label: 'cat', observed_at: at, status, reviewed_at: null,
        snapshot_url: `/api/garden/${id.padEnd(32, '0')}/snapshot` as string | null, crop_url: null as string | null, source_kind: 'frigate_event', motion_source: null,
        automatic_check: null, automatic_check_overridden: false,
        identification: name ? {
            outcome: 'suggestion', reason: 'confident', review: 'accepted', automatic: false, name, rank: 'species', score: 0.93,
            country: 'GBR', variant: '4.0.3b', provider: 'cpu', devices: ['cpu'], output_index: 1, input_kind: box ? 'tracked_crop' : 'whole_image', box_xywh: box ?? null,
            frame_size: [160, 120], identified_at: at
        } : null
    };
}

async function openExplorer(page: Page, query = '', cropped = false) {
    const errors: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    const visits = [bird('morning', hoursAgo(1)), bird('night', hoursAgo(5))];
    const garden = [capture('fox', hoursAgo(3), 'confirmed', 'Red fox', cropped ? [0.05, 0.1, 0.2, 0.3] : undefined), capture('cat', hoursAgo(0.5), 'pending')];
    const timelineQueries: URLSearchParams[] = [];
    const captureQueries: URLSearchParams[] = [];
    const confirmed: string[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/visits') {
            return route.fulfill({ json: { total: 2, gap_seconds: 60, visits: visits.map(record => ({
                visit_id: record.frigate_event, start_time: record.detection_time, end_time: record.detection_time, capture_count: 1,
                best_score: 0.91, needs_review: false, audio_confirmed: false, representative: record, latest: record, peak_capture: null
            })) } });
        }
        if (path === '/api/garden/visits' || (path.startsWith('/api/garden/visits/') && path.endsWith('/captures'))) {
            if (!path.endsWith('/captures')) timelineQueries.push(url.searchParams);
            else captureQueries.push(url.searchParams);
            return route.fulfill({ json: gardenVisitResponse(garden, url) });
        }
        if (path === '/api/garden/identification') {
            return route.fulfill({ json: { country: 'GBR', catalogue_ready: true, busy: false, models: [{ variant: '4.0.3b', installed: true, size_bytes: 1 }] } });
        }
        if (path.endsWith('/confirm')) {
            const id = path.split('/')[3];
            confirmed.push(id);
            const index = garden.findIndex(item => item.id === id);
            garden[index] = { ...garden[index], status: 'confirmed' };
            return route.fulfill({ json: garden[index] });
        }
        if (path.endsWith('/snapshot') || path.endsWith('/crop') || path.endsWith('.jpg')) {
            return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="#4d7c0f"/></svg>' });
        }
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 2, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
    await page.goto(`/browser-tests/owner-history.html?surface=explorer${query}`);
    await expect(page.locator('[data-explorer-visit="morning"]')).toBeVisible();
    return { errors, timelineQueries, captureQueries, confirmed, garden };
}

test('Garden captures sit between the visits they fell between, marked Garden in words', async ({ page }) => {
    const { errors, timelineQueries } = await openExplorer(page, '&garden=1');
    const order = page.locator('[data-explorer-visit], [data-garden-card]');
    await expect(order).toHaveCount(4);
    const kinds = await order.evaluateAll(nodes => nodes.map(node => node.getAttribute('data-explorer-visit') ?? `garden:${node.getAttribute('data-garden-card')}`));
    expect(kinds).toEqual(['garden:pending', 'morning', 'garden:confirmed', 'night']);
    await expect(page.locator('[data-garden-card="confirmed"]')).toContainText('Red fox');
    await expect(page.locator('[data-garden-card="pending"]')).toContainText('Waiting for automatic identification');
    await expect(page.locator('[data-garden-card] [data-garden-marker]').first()).toHaveText(/Garden/);
    expect(timelineQueries[0]?.get('order')).toBe('newest');
    if (shots) await page.screenshot({ path: `${shots}/garden-explorer-cards.png`, fullPage: true });

    await page.locator('[data-explorer-view-toggle="list"]').click();
    await expect(page.locator('[data-garden-row]')).toHaveCount(2);
    if (shots) await page.screenshot({ path: `${shots}/garden-explorer-list.png`, fullPage: true });
    expect(errors).toEqual([]);
});

test('Garden on its own lists only captures, and its record confirms an animal without bird actions', async ({ page }) => {
    const { errors, confirmed } = await openExplorer(page, '&garden=1');
    const option = page.locator('[data-explorer-subjects-option="garden"]');
    // On a phone the filter rail opens from the Filters button.
    if (!(await option.isVisible())) await page.locator('[data-explorer-filter-toggle]').click();
    await option.click();
    await expect(page.locator('[data-explorer-visit]')).toHaveCount(0);
    await expect(page.locator('[data-explorer-count]')).toContainText('Garden entries: 2 · captures: 2');

    await page.getByRole('button', { name: /Open Garden capture: Possible animal/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('Waiting for automatic identification');
    await expect(dialog.locator('[data-garden-capture-status]')).not.toHaveAttribute('data-garden-capture-status', 'confirmed');
    await expect(dialog.getByRole('button', { name: /Reclassify|Play/i })).toHaveCount(0);
    if (shots) await page.screenshot({ path: `${shots}/garden-explorer-record.png` });
    await expect(dialog.getByRole('button', { name: 'Confirm animal manually' })).not.toBeVisible();
    await dialog.getByText('Manual override', { exact: true }).click();
    await dialog.getByRole('button', { name: 'Confirm animal manually' }).click();
    await expect(dialog.locator('[data-garden-capture-status]')).toHaveAttribute('data-garden-capture-status', 'confirmed');
    await expect(dialog.locator('[data-garden-capture-status]')).toContainText('Animal confirmed');
    expect(confirmed).toEqual(['cat'.padEnd(32, '0')]);

    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    await expect(page.locator('[data-garden-card="confirmed"]')).toHaveCount(2);
    expect(errors).toEqual([]);
});

test('without the Garden beta the Explorer shows birds and asks for nothing about Garden', async ({ page }) => {
    const { timelineQueries } = await openExplorer(page);
    await expect(page.locator('[data-explorer-visitors-facet]')).toHaveCount(0);
    await expect(page.locator('[data-garden-card]')).toHaveCount(0);
    expect(timelineQueries).toEqual([]);
});


for (const gardenOnly of [false, true]) {
    test(`automatic Garden changes refresh the open record and privacy removal closes it (Garden only: ${gardenOnly})`, async ({ page }) => {
        const { garden, timelineQueries, errors } = await openExplorer(page, '&garden=1');
        if (gardenOnly) {
            const option = page.locator('[data-explorer-subjects-option="garden"]');
            if (!(await option.isVisible())) await page.locator('[data-explorer-filter-toggle]').click();
            await option.click();
            await expect(page.locator('[data-explorer-visit]')).toHaveCount(0);
        }
        await page.getByRole('button', { name: /Open Garden capture: Possible animal/ }).click();
        const dialog = page.getByRole('dialog');
        await expect(dialog).toContainText('Waiting for automatic identification');
        const previousReads = timelineQueries.length;
        const named = capture('cat', garden[1].observed_at, 'confirmed', 'Domestic cat');
        if (named.identification) named.identification.automatic = true;
        garden[1] = named;
        await page.evaluate(() => {
            window.dispatchEvent(new Event('fixture-garden-change'));
            window.dispatchEvent(new Event('fixture-garden-change'));
        });
        await expect(dialog).toContainText('Domestic cat');
        await expect(dialog.locator('[data-garden-capture-status]')).toHaveText('Confirmed and named automatically');
        expect(timelineQueries.length).toBe(previousReads + 1);
        garden.splice(1, 1);
        await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
        await expect(dialog).toHaveCount(0);
        await expect(page.locator('[data-garden-card]')).toHaveCount(1);
        expect(errors).toEqual([]);
    });
}


test('Garden cards, list previews and records crop to saved animal geometry with a whole-scene peek', async ({ page }) => {
    const { errors } = await openExplorer(page, '&garden=1', true);
    const preview = page.locator('[data-garden-card="confirmed"] [data-garden-preview="crop"] img');
    await expect(preview).toBeVisible();
    const geometry = await preview.evaluate(img => ({ width: img.getBoundingClientRect().width, container: img.parentElement?.getBoundingClientRect().width }));
    expect(geometry.width).toBeGreaterThan(geometry.container ?? 0);
    await expect(page.locator('[data-garden-card="pending"] [data-garden-preview="full"]')).toBeVisible();
    await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
    await expect(page.locator('[data-garden-capture-photo]')).toBeVisible();
    await page.getByRole('button', { name: 'Show whole photo', exact: true }).click();
    await expect(page.locator('[data-garden-capture-box]')).toBeVisible();
    await page.keyboard.press('Escape');
    await page.keyboard.press('Escape');
    await page.locator('[data-explorer-view-toggle="list"]').click();
    await expect(page.locator('[data-garden-row="confirmed"] [data-garden-preview="crop"]')).toBeVisible();
    expect(errors).toEqual([]);
});

test('a saved animal crop remains visible after full-photo expiry without becoming model input', async ({ page }) => {
    const { garden, errors } = await openExplorer(page, '&garden=1');
    const item = garden[0];
    item.snapshot_url = null;
    item.crop_url = `/api/garden/${item.id}/crop`;
    await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
    const card = page.locator('[data-garden-card="confirmed"]');
    await expect(card.locator('img')).toHaveAttribute('src', new RegExp(`${item.id}/crop`));
    await expect(card.locator('img')).toHaveCSS('object-fit', 'contain');
    await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.locator('[data-garden-saved-crop]')).toBeVisible();
    await expect(dialog.locator('[data-garden-capture-box]')).toHaveCount(0);
    await expect(dialog.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${item.id}/crop`));
    expect(errors).toEqual([]);
});


test('a reclaimed crop falls back to an available full photo', async ({ page }) => {
    const { garden } = await openExplorer(page, '&garden=1');
    const item = garden[0];
    item.crop_url = `/api/garden/${item.id}/crop`;
    await page.route('**/api/garden/*/crop*', route => route.fulfill({ status: 404, json: { detail: 'Crop unavailable' } }));
    await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
    const image = page.locator('[data-garden-card="confirmed"] img');
    await expect(image).toHaveAttribute('src', new RegExp(`${item.id}/snapshot`));
    await expect(image).toBeVisible();
    await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
    await expect(page.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${item.id}/snapshot`));
});

test('a Garden record opens its saved crop before the available original', async ({ page }) => {
    const { garden } = await openExplorer(page, '&garden=1');
    const item = garden[0];
    item.crop_url = `/api/garden/${item.id}/crop`;
    await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
    await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
    await expect(page.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${item.id}/crop`));
    await page.getByRole('button', { name: 'Show whole photo', exact: true }).click();
    await expect(page.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${item.id}/snapshot`));
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-garden-capture-modal]')).toBeVisible();
    await expect(page.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${item.id}/crop`));
});

test('the manual CPU choice does not describe the saved SpeciesNet result', async ({ page }) => {
    const { garden } = await openExplorer(page, '&garden=1');
    garden[0].identification = null;
    await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
    await page.getByRole('button', { name: /Open Garden capture: Animal/ }).click();
    const dialog = page.locator('[data-garden-capture-modal]');
    await expect(dialog.getByRole('button', { name: 'Suggest species', exact: true })).toBeVisible();
    await expect(dialog.locator('[data-garden-capture-actions]')).not.toContainText('Runs SpeciesNet');
    await expect(dialog.locator('[data-garden-capture-model]')).toBeHidden();
    await dialog.locator('[data-garden-capture-details] summary').click();
    await expect(dialog.locator('[data-garden-capture-model]')).toContainText('New manual suggestion');
});

test('a Garden visit offers selectable crop thumbnails rather than sequential photo buttons', async ({ page }, testInfo) => {
    const { garden, errors } = await openExplorer(page, '&garden=1');
    const first = garden[0];
    first.crop_url = `/api/garden/${first.id}/crop`;
    const second = capture('fox2', new Date(Date.parse(first.observed_at) + 10_000).toISOString(), 'confirmed', 'Red fox');
    second.crop_url = `/api/garden/${second.id}/crop`;
    garden.push(second);
    await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
    await expect(page.locator('[data-garden-card-group]')).toHaveText('2 captures in this visit');
    await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
    const dialog = page.locator('[data-garden-capture-modal]');
    await expect(dialog.locator('[data-garden-capture-choice]')).toHaveCount(2);
    const choice = dialog.locator(`[data-garden-capture-choice="${first.id}"]`);
    await expect(choice.locator('img')).toHaveAttribute('src', new RegExp(`${first.id}/crop`));
    await choice.click();
    await expect(choice).toHaveAttribute('aria-pressed', 'true');
    await expect(dialog.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${first.id}/crop`));
    await expect(dialog.getByRole('button', { name: /^(Previous|Next) photo$/ })).toHaveCount(0);
    if (shots) await page.screenshot({ path: `${shots}/garden-record-crops-${testInfo.project.name}.png` });
    expect(errors).toEqual([]);
});


for (const [provider, device] of [['cpu', 'CPU'], ['intel_npu', 'NPU']] as const) {
    test(`the capture keeps its recorded ${device} evidence independently of the current device preference`, async ({ page }) => {
        const { garden } = await openExplorer(page, '&garden=1');
        const identity = garden[0].identification;
        if (!identity) throw new Error('Expected a saved identification');
        identity.provider = provider;
        identity.devices = [device];
        identity.automatic = true;
        await page.route('**/api/garden/identification', route => route.fulfill({ json: {
            country: 'GBR', catalogue_ready: true, busy: false, preferred_provider: 'intel_npu',
            last_execution: { provider: 'intel_npu', devices: ['NPU'], checked_at: new Date().toISOString() },
            models: [{ variant: '4.0.3b', installed: true, size_bytes: 1 }]
        } }));
        await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
        await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
        await page.locator('[data-garden-capture-details] summary').click();
        const evidence = page.locator('[data-garden-capture-identification]');
        await expect(evidence).toContainText(`SpeciesNet 4.0.3b · ${device}`);
        await expect(evidence).toContainText('GBR');
    });
}

test('confirmed visit dismissal sends only the displayed review snapshots and offers return to review', async ({ page }) => {
    const { garden, errors } = await openExplorer(page, '&garden=1', true);
    const first = garden[0];
    first.id = '1'.repeat(32);
    Object.assign(first, { review_token: 'a'.repeat(64) });
    const second = capture('2'.repeat(32), new Date(Date.parse(first.observed_at) + 7_000).toISOString(), 'confirmed', 'Red fox');
    Object.assign(second, { review_token: 'b'.repeat(64) });
    garden.push(second);
    let submitted: unknown = null;
    let release = (): void => {};
    const complete = new Promise<void>((resolve) => { release = resolve; });
    await page.route('**/api/garden/dismiss-captures', async route => {
        submitted = route.request().postDataJSON();
        await complete;
        garden.splice(garden.indexOf(first), 1);
        garden.splice(garden.indexOf(second), 1);
        return route.fulfill({ json: { updated_ids: [first.id, second.id], skipped_count: 0 } });
    });
    await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
    await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
    const dialog = page.locator('[data-garden-capture-modal]');
    await dialog.getByRole('button', { name: 'Dismiss 2 captures in this visit' }).click();
    try {
        await expect(dialog).toHaveAttribute('aria-busy', 'true');
        await page.keyboard.press('Escape');
        await expect(dialog).toBeVisible();
    } finally { release(); }
    expect(submitted).toEqual({ captures: [
        { id: first.id, review_token: 'a'.repeat(64) }, { id: second.id, review_token: 'b'.repeat(64) }
    ] });
    await expect(dialog).toBeHidden();
    await expect(page.locator('[data-explorer-garden-undo]').getByRole('button', { name: 'Return captures to review' })).toBeVisible();
    expect(errors).toEqual([]);
});

for (const knownIdentity of [true, false]) {
    test(`a dog's reference is bound to its catalogue identity (${knownIdentity ? 'known' : 'unavailable'})`, async ({ page }) => {
        await page.setViewportSize({ width: 390, height: 1000 });
        const { garden, errors } = await openExplorer(page, '&garden=1', true);
        const dog = garden[0];
        if (!dog.identification) throw new Error('Expected a saved identification');
        dog.identification.name = 'Domestic Dog';
        Object.assign(dog, { scientific_name: knownIdentity ? 'Canis familiaris' : null });
        const requests: string[] = [];
        await page.route('**/api/species/*/info*', route => {
            const scientificName = new URL(route.request().url()).searchParams.get('scientific_name');
            requests.push(scientificName ?? '');
            const matches = scientificName === 'Canis familiaris';
            return route.fulfill({ json: {
                title: matches ? 'Dog' : 'Cessna O-1 Bird Dog',
                description: null, extract: matches ? 'The dog is a domesticated mammal.' : 'A liaison and observation aircraft.',
                thumbnail_url: matches ? '/api/reference-dog.jpg' : '/api/aircraft.jpg', scientific_name: scientificName,
                source: 'Wikipedia', summary_source: 'Wikipedia'
            } });
        });
        await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
        await page.getByRole('button', { name: /Open Garden capture: Domestic Dog/ }).click();
        const dialog = page.locator('[data-garden-capture-modal]');
        if (knownIdentity) {
            await expect(dialog.locator('[data-garden-species-info]')).toContainText('domesticated mammal');
            await expect(dialog.locator('[data-garden-species-reference]')).toHaveAttribute('src', '/api/reference-dog.jpg');
            expect(requests).toEqual(['Canis familiaris']);
        } else {
            await expect(dialog.locator('[data-garden-capture-details] summary')).toBeVisible();
            await expect(dialog.locator('[data-garden-species-info]')).toHaveCount(0);
            expect(requests).toEqual([]);
        }
        await expect(dialog).not.toContainText('aircraft');
        expect(errors).toEqual([]);
    });
}

for (const width of [390, 1280]) {
    test(`a named animal's record reads like a bird's: catalogue names, lineage, one state and closed details at ${width}px`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width, height: 1000 });
        const { garden, errors } = await openExplorer(page, '&garden=1', true);
        const fox = garden[0];
        if (!fox.identification) throw new Error('Expected a saved identification');
        fox.identification.automatic = true;
        Object.assign(fox, { scientific_name: 'Vulpes vulpes', automatic_check: {
            outcome: 'animal', checked_at: fox.observed_at, devices: ['NPU'], variant: '4.0.3a', decision_reason: null
        } });
        const companion = capture('fox2', new Date(Date.parse(fox.observed_at) + 7_000).toISOString(), 'confirmed', 'Red fox', [0.05, 0.1, 0.2, 0.3]);
        garden.push(companion);
        const speciesReads: string[] = [];
        await page.route('**/api/species/*/info?*', route => {
            expect(new URL(route.request().url()).searchParams.get('scientific_name')).toBe('Vulpes vulpes');
            speciesReads.push(decodeURIComponent(new URL(route.request().url()).pathname.split('/')[3]));
            return route.fulfill({ json: {
                title: 'Red fox', description: null, extract: 'The red fox is the largest of the true foxes.',
                thumbnail_url: '/api/garden/reference/snapshot', wikipedia_url: null, source: 'Wikipedia', source_url: null,
                summary_source: 'Wikipedia', summary_source_url: 'https://en.wikipedia.org/wiki/Red_fox',
                scientific_name: 'Vulpes vulpes', conservation_status: null, cached_at: null
            } });
        });
        await page.route('**/api/taxonomy/lineage?*', route => route.fulfill({ json: { lineage: [
            { taxon_id: 1, rank: 'class', scientific_name: 'Mammalia', name: 'Mammals', principal: true },
            { taxon_id: 2, rank: 'order', scientific_name: 'Carnivora', name: 'Carnivores', principal: true },
            { taxon_id: 3, rank: 'family', scientific_name: 'Canidae', name: 'Dogs', principal: true },
            { taxon_id: 4, rank: 'genus', scientific_name: 'Vulpes', name: null, principal: true },
            { taxon_id: 5, rank: 'species', scientific_name: 'Vulpes vulpes', name: 'Red fox', principal: true }
        ] } }));
        await page.evaluate(() => window.dispatchEvent(new Event('fixture-garden-change')));
        await page.getByRole('button', { name: /Open Garden capture: Red fox/ }).click();
        const dialog = page.locator('[data-garden-capture-modal]');

        const identity = dialog.locator('[data-garden-capture-identity]');
        await expect(identity.getByRole('heading', { name: 'Red fox', level: 3 })).toBeVisible();
        await expect(identity.locator('[data-garden-scientific-name]')).toHaveText('Vulpes vulpes');
        await expect(identity.locator('[data-garden-named-from]')).toHaveText("Named from Frigate's tracked animal in the snapshot");
        await expect(identity.locator('[data-garden-species-reference]')).toBeVisible();
        await expect(dialog.locator('[data-garden-capture-status]')).toHaveText('Confirmed and named automatically');
        await expect(dialog.locator('[data-taxonomy-ladder]')).toContainText('Canidae');
        await expect(dialog.locator('[data-garden-species-info]')).toContainText('largest of the true foxes');
        expect(speciesReads).toContain('Red fox');

        // The state is said once; the model run and manual choices wait behind Details.
        await expect(dialog.getByText('Confident animal. Confirmed and named automatically', { exact: false })).toBeHidden();
        await expect(dialog.locator('[data-garden-capture-model]')).toBeHidden();
        await dialog.locator('[data-garden-capture-details] summary').click();
        await expect(dialog.locator('[data-garden-capture-identification]')).toContainText('SpeciesNet 4.0.3b');
        await expect(dialog.locator('[data-garden-automatic-check]')).toBeVisible();

        // Captures seconds apart are told apart by their seconds.
        const times = await dialog.locator('[data-garden-capture-choice] span').allInnerTexts();
        expect(new Set(times).size).toBe(2);
        await expect(dialog.locator('[data-garden-capture-dismiss]')).toHaveClass(/btn-ghost/);

        await page.screenshot({ path: testInfo.outputPath(`garden-record-${width}.png`), fullPage: true });
        if (shots) await page.screenshot({ path: `${shots}/garden-record-parity-${width}.png` });
        expect(errors).toEqual([]);
    });
}


for (const mode of ['cards', 'list']) {
    test(`Garden ${mode} capture details page independently and open the exact selected photo`, async ({ page }) => {
        const { garden, errors, captureQueries } = await openExplorer(page, '&garden=1');
        const at = Date.parse(garden[0].observed_at);
        garden.splice(0, 1, ...Array.from({ length: 26 }, (_, index) => capture(
            (index + 1).toString(16).padStart(32, '0'), new Date(at + index * 1000).toISOString(), 'confirmed', 'Red fox'
        )).map(item => ({ ...item, crop_url: `/api/garden/${item.id}/crop` })));
        await page.reload();
        if (mode === 'list') await page.locator('[data-explorer-view-toggle="list"]').click();
        expect(captureQueries).toHaveLength(0);
        const toggle = page.locator('[data-garden-visit-captures-toggle]');
        await toggle.focus();
        await page.keyboard.press('Enter');
        const panelId = await toggle.getAttribute('aria-controls');
        const panel = page.locator(`[id="${panelId}"]`);
        await expect(panel).toBeVisible();
        await expect(panel.locator('[data-garden-visit-capture]')).toHaveCount(20);
        expect(captureQueries[0].get('limit')).toBe('20');
        await panel.getByRole('button', { name: 'Load more captures', exact: true }).click();
        await expect(panel.locator('[data-garden-visit-capture]')).toHaveCount(26);
        expect(captureQueries[1].get('offset')).toBe('20');
        const chosen = panel.locator('[data-garden-visit-capture]').nth(23);
        const chosenId = await chosen.getAttribute('data-garden-visit-capture');
        await expect(chosen.locator('time')).toHaveText(/\d{2}:\d{2}:\d{2}/);
        await chosen.getByRole('button').click();
        const modal = page.locator('[data-garden-capture-modal]');
        await expect(modal).toBeVisible();
        await expect(modal.locator(`[data-garden-capture-choice="${chosenId}"]`)).toHaveAttribute('aria-pressed', 'true');
        await expect(modal.locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${chosenId}/crop`));
        expect(errors).toEqual([]);
    });
}
