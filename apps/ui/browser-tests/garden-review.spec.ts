import { gardenVisitResponse } from './garden-visits-fixture';
import { expect, test, type Page, type Route } from '@playwright/test';

// Garden review happens in the Explorer: Garden visitors in the filter rail, one review state at a
// time, and each capture or position group opened in its Garden record. These scenarios carried over
// from the retired Garden page, so the review guarantees stay proven where the work now happens.

type Capture = Record<string, unknown> & { id: string };

const modelStatus = { country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [{ variant: '4.0.3b', installed: true, size_bytes: 223999179 }] };
const motionStatus = { cameras: [], installed: false, catalogue_ready: true, busy: false, state: 'disabled', message: 'Motion collection is off.' };

const id = 'a'.repeat(32);
const row: Capture = {
    id, camera: 'patio', frigate_label: 'cat', observed_at: '2026-10-11T18:00:00Z', reviewed_at: null, status: 'pending',
    snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'frigate_event', motion_source: null, identification: null,
    automatic_check: null, automatic_check_overridden: false
};
const motionSource = {
    camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1,
    clip_sha256: 'a'.repeat(64), image_sha256: 'b'.repeat(64), detector_sha256: 'c'.repeat(64),
    detector_score: 0.8, box_xywh: [0.1, 0.2, 0.3, 0.4]
};
const photo = (width: number, height: number) => `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}"><rect width="100%" height="100%" fill="#28594a"/></svg>`;

interface Mock {
    /** Captures for a requested review state; `reviewable` is the default animals view. */
    items: (status: string) => Capture[];
    identification?: Record<string, unknown>;
    snapshot?: (route: Route) => Promise<void>;
}

/** The HTTP boundary every scenario shares. Routes a test adds afterwards take precedence. */
async function mockGarden(page: Page, mock: Mock) {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/garden/visits' || (path.startsWith('/api/garden/visits/') && path.endsWith('/captures'))) {
            const items = mock.items(url.searchParams.get('status') ?? 'reviewable');
            return route.fulfill({ json: gardenVisitResponse(items, url) });
        }
        if (path === '/api/garden/identification') return route.fulfill({ json: mock.identification ?? modelStatus });
        if (path === '/api/garden/motion') return route.fulfill({ json: motionStatus });
        if (path.endsWith('/snapshot')) return mock.snapshot ? mock.snapshot(route) : route.fulfill({ contentType: 'image/svg+xml', body: photo(1280, 720) });
        if (path === '/api/visits') return route.fulfill({ json: { total: 0, gap_seconds: 60, visits: [] } });
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 0, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
}

/** On a phone the rail sits behind the Filters button, so open it the way a person would. */
async function revealRail(page: Page) {
    const facet = page.locator('[data-explorer-garden-review-facet]');
    await expect(facet).toBeAttached();
    if (!(await facet.isVisible())) await page.locator('[data-explorer-filter-toggle]').click();
    await expect(facet).toBeVisible();
}

async function openReview(page: Page, review: 'pending' | 'confirmed' | 'dismissed' = 'pending') {
    await page.goto(`/browser-tests/owner-history.html?surface=explorer&garden=1&visitors=garden&review=${review}`);
    await expect(page.locator('[data-explorer-garden-review-facet]')).toBeAttached();
}

const record = (page: Page) => page.locator('[data-garden-capture-modal]');
const toasts = (page: Page) => page.locator('[data-toast-container]');

async function nextPhoto(page: Page) {
    await expect(record(page).locator('[data-garden-capture-group] [role="group"]')).toHaveAttribute('aria-busy', 'false');
    const choices = record(page).locator('[data-garden-capture-choice]');
    const selected = await choices.evaluateAll(nodes => nodes.findIndex(node => node.getAttribute('aria-pressed') === 'true'));
    expect(selected).toBeGreaterThanOrEqual(0);
    if (selected + 1 < await choices.count()) await choices.nth(selected + 1).click();
    else await record(page).getByRole('button', { name: 'More photos', exact: true }).click();
}


async function openFirst(page: Page) {
    await page.locator('[data-garden-card]').first().getByRole('button', { name: /^Open Garden capture/ }).click();
    await expect(record(page)).toBeVisible();
    const override = record(page).locator('[data-garden-manual-override]');
    if (await override.count() && !(await override.evaluate(node => (node as HTMLDetailsElement).open))) {
        await override.locator('summary').click();
    }
}

async function chooseReview(page: Page, review: 'pending' | 'confirmed' | 'dismissed') {
    await revealRail(page);
    await page.locator(`[data-explorer-garden-review="${review}"]`).click();
}

async function fitsNarrowScreen(page: Page) {
    await page.setViewportSize({ width: 320, height: 740 });
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
}

async function wideAgain(page: Page) {
    await page.evaluate(() => document.documentElement.style.fontSize = '');
    await page.setViewportSize({ width: 1280, height: 900 });
}

test('automatic rejections explain the result and can return to review without another photo check', async ({ page }) => {
    let status = 'dismissed';
    let photoChecks = 0;
    const automatic = {
        outcome: 'non_animal', checked_at: '2026-10-20T19:00:00', variant: '4.0.3a',
        image_sha256: 'b'.repeat(64), model_sha256: 'c'.repeat(64), package_sha256: 'd'.repeat(64),
        mass: { bird: 0.01, animal: 0.01, human: 0.001, non_animal: 0.97, other: 0.009 },
        box_xywh: [0.1, 0.2, 0.3, 0.4], devices: ['CPUExecutionProvider']
    };
    await mockGarden(page, { items: requested => requested === status ? [{ ...row, status, automatic_check: automatic, automatic_check_overridden: status === 'pending' }] : [] });
    await page.route('**/api/garden/*/check-photo', route => { photoChecks++; return route.abort(); });
    await page.route('**/api/garden/*/restore', route => { status = 'pending'; return route.fulfill({ json: { ...row, status, automatic_check: automatic, automatic_check_overridden: true } }); });
    await openReview(page, 'dismissed');
    await openFirst(page);
    await expect(record(page).locator('[data-garden-automatic-check]')).toContainText('Blank scene or vehicle suggested.');
    await fitsNarrowScreen(page);
    await record(page).getByRole('button', { name: 'Return to review' }).click();
    await expect(record(page)).toHaveCount(0);
    await wideAgain(page);
    await chooseReview(page, 'pending');
    await openFirst(page);
    await expect(record(page).locator('[data-garden-automatic-check]')).toContainText('Your review overrides this automatic result.');
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
    expect(photoChecks).toBe(0);
});

test('an automatically named animal says so, and its name and presence can each be undone', async ({ page }) => {
    const actions: string[] = [];
    const automatic = {
        outcome: 'animal', checked_at: '2026-10-21T23:46:45', variant: '4.0.3a',
        image_sha256: 'b'.repeat(64), model_sha256: 'c'.repeat(64), package_sha256: 'd'.repeat(64),
        mass: { bird: 0, animal: 0.97, human: 0.001, non_animal: 0.01, other: 0.019 },
        box_xywh: [0.1, 0.2, 0.3, 0.4], devices: ['CPUExecutionProvider']
    };
    const named = {
        outcome: 'suggestion', reason: 'garden', review: 'accepted', automatic: true, taxon_id: 'cat', species_id: 1807,
        name: 'domestic cat', rank: 'species', score: 0.93, geofenced: false, country: 'GBR', variant: '4.0.3a',
        provider: 'cpu', devices: ['CPUExecutionProvider'], model_sha256: 'c'.repeat(64), package_sha256: 'd'.repeat(64),
        image_sha256: 'b'.repeat(64), output_index: 1806, input_kind: 'tracked_crop', box_xywh: [0.1, 0.2, 0.3, 0.4],
        frame_size: [640, 480], identified_at: '2026-10-21T23:46:45Z'
    };
    const confirmed = { ...row, status: 'confirmed', automatic_check: automatic, identification: named };
    await mockGarden(page, { items: requested => (requested === 'confirmed' ? [confirmed] : []) });
    await page.route('**/api/garden/*/identification/*', route => {
        actions.push(new URL(route.request().url()).pathname.split('/').pop() ?? '');
        return route.fulfill({ json: { ...confirmed, identification: { ...named, review: 'dismissed' } } });
    });
    await openReview(page, 'confirmed');
    await expect(page.locator('[data-garden-card]')).toContainText('Named automatically');
    await openFirst(page);
    await expect(record(page).getByRole('heading', { name: 'domestic cat', level: 3 })).toBeVisible();
    await expect(record(page).locator('[data-garden-capture-status]')).toHaveText('Confirmed and named automatically');
    await expect(record(page).locator('[data-garden-capture-status]')).not.toHaveText('Animal and species confirmed by you');
    await expect(record(page).locator('[data-garden-automatic-check]')).toContainText('Confident animal. Confirmed and named automatically');
    await expect(record(page).getByRole('button', { name: 'Dismiss capture' })).toBeEnabled();
    await record(page).getByRole('button', { name: 'Discard identification' }).click();
    await expect.poll(() => actions).toEqual(['dismiss']);
});

for (const size of [[640, 1000], [1280, 720], [1600, 400]]) {
    test(`presence proposal aligns with the ${size.join('x')} photo before species analysis`, async ({ page }) => {
        await mockGarden(page, {
            items: requested => (requested === 'pending' ? [{ ...row, source_kind: 'motion', motion_source: motionSource }] : []),
            snapshot: route => route.fulfill({ contentType: 'image/svg+xml', body: photo(size[0], size[1]) })
        });
        await openReview(page);
        await openFirst(page);
        await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
        await expect(record(page).getByText('Box: MegaDetector Cedar candidate. Check the photo before confirming.')).toBeVisible();
        for (const width of [1280, 320]) {
            await page.setViewportSize({ width, height: 900 });
            await page.evaluate(() => document.documentElement.style.fontSize = '200%');
            const peek = record(page).getByRole('button', { name: 'Show whole photo', exact: true });
            if (await peek.getAttribute('aria-pressed') !== 'true') await peek.click();
            await expect(record(page).locator('[data-garden-capture-box] rect').last()).toBeVisible();
            // Measured together: a late font load can move the record between two browser calls.
            const { image, outline } = await record(page).evaluate(node => {
                const picture = node.querySelector('[data-garden-capture-photo]');
                const box = node.querySelector('[data-garden-capture-box] rect:last-child');
                if (!picture || !box) throw new Error('Expected a decoded photo and detector proposal');
                return { image: picture.getBoundingClientRect().toJSON(), outline: box.getBoundingClientRect().toJSON() };
            });
            const scale = Math.min(image.width / size[0], image.height / size[1]);
            // DOM rect geometry excludes the outline's non-scaling paint stroke.
            expect(outline.x).toBeCloseTo(image.x + (image.width - size[0] * scale) / 2 + size[0] * 0.1 * scale, 1);
            expect(outline.y).toBeCloseTo(image.y + (image.height - size[1] * scale) / 2 + size[1] * 0.2 * scale, 1);
            expect(outline.width).toBeCloseTo(size[0] * 0.3 * scale, 1);
            expect(outline.height).toBeCloseTo(size[1] * 0.4 * scale, 1);
            await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
    });
}

test('failed motion photo hides its box and blocks presence confirmation', async ({ page }) => {
    await mockGarden(page, {
        items: requested => (requested === 'pending' ? [{ ...row, source_kind: 'motion', motion_source: motionSource }] : []),
        snapshot: route => route.fulfill({ status: 404 })
    });
    await openReview(page);
    await openFirst(page);
    await expect(record(page).getByText('Snapshot unavailable')).toBeVisible();
    await expect(record(page).locator('[data-garden-capture-box]')).toHaveCount(0);
    await expect(record(page).getByText('Box: MegaDetector Cedar candidate. Check the photo before confirming.')).toHaveCount(0);
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeDisabled();
});

for (const sourceKind of ['motion', 'frigate_event']) {
    for (const photoAvailable of [true, false]) {
        test(`dismissed ${sourceKind} photo ${photoAvailable ? 'can return to review' : 'explains why restoration is unavailable'}`, async ({ page }) => {
            let status = 'dismissed';
            let writes = 0;
            await mockGarden(page, {
                items: requested => (requested === status ? [{ ...row, status, source_kind: sourceKind, snapshot_url: photoAvailable ? row.snapshot_url : null }] : [])
            });
            await page.route('**/api/garden/*/restore', route => {
                writes++;
                status = 'pending';
                return route.fulfill({ json: { ...row, source_kind: sourceKind, status } });
            });
            await openReview(page, 'dismissed');
            await openFirst(page);
            const restore = record(page).getByRole('button', { name: 'Return to review' });
            if (photoAvailable) {
                await expect(restore).toBeEnabled();
                await restore.click();
                await expect(toasts(page)).toContainText('Photo returned to review.');
                await chooseReview(page, 'pending');
                await openFirst(page);
                await expect(record(page).getByText(sourceKind === 'motion' ? 'Candidate from retained motion footage' : 'Frigate suggested: cat')).toBeVisible();
                expect(writes).toBe(1);
            } else {
                await expect(restore).toBeDisabled();
                await expect(record(page).getByText('Photo unavailable. It cannot return to review.')).toBeVisible();
                expect(writes).toBe(0);
            }
            await fitsNarrowScreen(page);
        });
    }
}

test('owner can dismiss a false capture, restore it and review at narrow widths', async ({ page }) => {
    let status = 'pending';
    await mockGarden(page, { items: requested => (requested === status ? [{ ...row, status }] : []), snapshot: route => route.fulfill({ status: 404 }) });
    await page.route(/\/api\/garden\/[^/]+\/(dismiss|restore)$/, route => {
        status = route.request().url().endsWith('/dismiss') ? 'dismissed' : 'pending';
        return route.fulfill({ json: { ...row, status } });
    });
    await openReview(page);
    await openFirst(page);
    await expect(record(page).getByText('Frigate suggested: cat')).toBeVisible();
    await expect(record(page).getByText('Snapshot unavailable')).toBeVisible();
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeDisabled();
    await record(page).getByRole('button', { name: 'Dismiss capture' }).click();
    await expect(record(page)).toHaveCount(0);
    await expect(page.getByText('No Garden captures need review')).toBeVisible();
    await chooseReview(page, 'dismissed');
    await openFirst(page);
    await record(page).getByRole('button', { name: 'Return to review' }).click();
    await chooseReview(page, 'pending');
    await openFirst(page);
    await expect(record(page).getByText('Frigate suggested: cat')).toBeVisible();
    await fitsNarrowScreen(page);
});

test('owner confirms presence only after the photo loads', async ({ page }) => {
    let confirmed = false;
    await mockGarden(page, {
        items: requested => ((requested === 'confirmed') === confirmed && requested !== 'dismissed' ? [{ ...row, status: confirmed ? 'confirmed' : 'pending' }] : []),
        snapshot: route => route.fulfill({ contentType: 'image/svg+xml', body: photo(640, 360) })
    });
    await page.route('**/api/garden/*/confirm', route => { confirmed = true; return route.fulfill({ json: { ...row, status: 'confirmed' } }); });
    await openReview(page);
    await openFirst(page);
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
    await record(page).getByRole('button', { name: 'Confirm animal manually' }).click();
    await expect(record(page)).toHaveCount(0);
    await expect(page.getByText('No Garden captures need review')).toBeVisible();
    await chooseReview(page, 'confirmed');
    await openFirst(page);
    await expect(record(page).getByText('Frigate suggested: cat')).toBeVisible();
    expect(confirmed).toBe(true);
});

test('a failed read is visible and Try again recovers', async ({ page }) => {
    let failed = true;
    await mockGarden(page, { items: () => [] });
    await page.route('**/api/garden/visits?**', route => route.fulfill(failed
        ? { status: 503, json: { detail: 'History temporarily unavailable' } }
        : { json: { visits: [], total: 0, capture_total: 0, limit: 24, offset: 0 } }));
    await openReview(page);
    const alert = page.getByRole('alert').filter({ hasText: 'The visits could not be loaded. Your history is unchanged.' });
    const retry = alert.getByRole('button', { name: 'Try again', exact: true });
    await expect(retry).toBeVisible();
    // A failed read is never an empty review queue.
    await expect(page.getByText('No Garden captures need review')).toHaveCount(0);
    failed = false;
    await retry.click();
    await expect(page.getByText('No Garden captures need review')).toBeVisible();
});

for (const outcome of ['species', 'group', 'unknown'] as const) {
    test(`owner reviews a ${outcome} suggestion without changing animal presence`, async ({ page }) => {
        let suggestion: Record<string, unknown> | null = null;
        const actions: string[] = [];
        const name = outcome === 'group' ? 'canidae' : 'red fox';
        await mockGarden(page, {
            items: requested => (requested === 'confirmed' ? [{ ...row, status: 'confirmed', identification: suggestion }] : []),
            snapshot: route => route.fulfill({ contentType: 'image/svg+xml', body: photo(640, 360) })
        });
        await page.route(/\/api\/garden\/[^/]+\/(identify|identification\/(accept|dismiss))$/, route => {
            const path = new URL(route.request().url()).pathname;
            actions.push(path);
            if (path.endsWith('/identify')) {
                expect(route.request().headers()['content-type']).toBe('application/json');
                expect(route.request().postDataJSON()).toEqual({ variant: '4.0.3b', provider: 'cpu' });
                suggestion = { outcome: outcome === 'unknown' ? 'unknown' : 'suggestion', reason: 'garden', review: 'unreviewed', name, rank: outcome === 'group' ? 'family' : 'species', score: 0.91, variant: '4.0.3b', provider: 'cpu', devices: ['CPUExecutionProvider'], country: 'GBR', output_index: 1, input_kind: 'whole_image', box_xywh: null, frame_size: [640, 360], identified_at: '2026-10-11T18:01:00Z' };
            } else if (suggestion) suggestion = { ...suggestion, review: path.endsWith('/accept') ? 'accepted' : 'dismissed' };
            return route.fulfill({ json: { ...row, status: 'confirmed', identification: suggestion } });
        });
        await openReview(page, 'confirmed');
        await openFirst(page);
        await expect(record(page).getByRole('button', { name: 'Suggest species', exact: true })).toBeEnabled();
        await record(page).getByRole('button', { name: 'Suggest species', exact: true }).click();
        if (outcome === 'unknown') {
            await expect(record(page).getByText(/No reliable identification/)).toBeVisible();
            await expect(record(page).getByRole('button', { name: `Confirm ${name}`, exact: true })).toHaveCount(0);
        } else {
            if (outcome === 'group') await expect(record(page).getByText('Animal group only; species is unresolved.')).toBeVisible();
            await record(page).getByRole('button', { name: `Confirm ${name}`, exact: true }).click();
            await expect(record(page).locator('[data-garden-capture-status]')).toHaveText('Animal and species confirmed by you');
            await record(page).getByRole('button', { name: 'Discard identification', exact: true }).click();
            await expect(record(page).locator('[data-garden-capture-status]')).toHaveText('Animal confirmed, species not named');
        }
        expect(actions.every(path => path.endsWith('/identify') || path.includes('/identification/'))).toBe(true);
        await fitsNarrowScreen(page);
    });
}

test('bird preemption is explained and does not manufacture a suggestion', async ({ page }) => {
    await mockGarden(page, {
        items: requested => (requested === 'confirmed' ? [{ ...row, status: 'confirmed' }] : []),
        snapshot: route => route.fulfill({ contentType: 'image/svg+xml', body: photo(10, 10) })
    });
    await page.route('**/api/garden/*/identify', route => route.fulfill({ status: 409, json: { detail: 'Bird inference needs the hardware. Try again when it is idle.' } }));
    await openReview(page, 'confirmed');
    await openFirst(page);
    await record(page).getByRole('button', { name: 'Suggest species', exact: true }).click();
    await expect(record(page).getByRole('alert')).toContainText('Bird inference needs the hardware');
    await expect(record(page).getByRole('button', { name: /^Confirm red fox/ })).toHaveCount(0);
});

test('a model that is not downloaded points to Settings instead of downloading from review', async ({ page }) => {
    const posts: string[] = [];
    await mockGarden(page, {
        items: requested => (requested === 'confirmed' ? [{ ...row, status: 'confirmed' }] : []),
        identification: { ...modelStatus, models: [{ ...modelStatus.models[0], installed: false }] }
    });
    page.on('request', request => { if (request.method() === 'POST') posts.push(new URL(request.url()).pathname); });
    await openReview(page, 'confirmed');
    await openFirst(page);
    await expect(record(page).getByText('This model is not downloaded. Download it under Garden models in Settings → Beta features.')).toBeVisible();
    await expect(record(page).getByRole('button', { name: 'Suggest species', exact: true })).toBeDisabled();
    await expect(page.getByRole('button', { name: /^Download/ })).toHaveCount(0);
    expect(posts).toEqual([]);
});

test('tracked crop outline stays on the photographed pixels with letterboxing', async ({ page }) => {
    const identification = { outcome: 'suggestion', reason: 'garden', review: 'unreviewed', name: 'red fox', rank: 'species', score: 0.9, variant: '4.0.3a', provider: 'intel_npu', devices: ['NPU'], country: 'GBR', output_index: 1, input_kind: 'tracked_crop', box_xywh: [0.1, 0.2, 0.3, 0.4], frame_size: [640, 1000], identified_at: '2026-10-11T18:01:00Z' };
    await mockGarden(page, {
        items: requested => (requested === 'confirmed' ? [{ ...row, status: 'confirmed', identification }] : []),
        snapshot: route => route.fulfill({ contentType: 'image/svg+xml', body: photo(640, 1000) })
    });
    await openReview(page, 'confirmed');
    await openFirst(page);
    await expect(record(page).locator('[data-garden-named-from]')).toHaveText("Named from Frigate's tracked animal in the snapshot");
    for (const width of [320, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        const peek = record(page).getByRole('button', { name: 'Show whole photo', exact: true });
            if (await peek.getAttribute('aria-pressed') !== 'true') await peek.click();
            await expect(record(page).locator('[data-garden-capture-box] rect').last()).toBeVisible();
        const image = await record(page).locator('[data-garden-capture-photo]').boundingBox();
        const outline = await record(page).locator('[data-garden-capture-box] rect').last().boundingBox();
        if (!image || !outline) throw new Error('Expected the photo and its input outline');
        const scale = Math.min(image.width / 640, image.height / 1000);
        // The visible 2px non-scaling stroke extends 1px beyond each crop edge.
        expect(outline.x).toBeCloseTo(image.x + (image.width - 640 * scale) / 2 + 64 * scale - 1, 1);
        expect(outline.y).toBeCloseTo(image.y + (image.height - 1000 * scale) / 2 + 200 * scale - 1, 1);
        expect(outline.width).toBeCloseTo(192 * scale + 2, 1);
        expect(outline.height).toBeCloseTo(400 * scale + 2, 1);
    }
});

test('motion proposals name their source, never as a Frigate label', async ({ page }) => {
    await mockGarden(page, {
        items: requested => (requested === 'pending' ? [{ ...row, source_kind: 'motion', frigate_label: 'animal' }] : []),
        snapshot: route => route.fulfill({ status: 404 })
    });
    await openReview(page);
    await openFirst(page);
    await expect(record(page).getByText('Candidate from retained motion footage')).toBeVisible();
    await expect(record(page).getByText('Frigate suggested: animal')).toHaveCount(0);
    await fitsNarrowScreen(page);
});

test('feeder box extent changes keep photos together with their original boxes', async ({ page }) => {
    const boxes = [
        [0.7787210464, 0.6029235840, 0.0294397354, 0.0996236165],
        [0.7807638645, 0.6024082184, 0.0539882183, 0.0722991943],
        [0.7797590256, 0.6019916534, 0.0315879822, 0.1271631241],
        [0.7814696312, 0.6021912893, 0.0293195724, 0.0882186254]
    ];
    const captures = boxes.map((box, index) => ({ ...row, id: String(index).padStart(32, '0'),
        snapshot_url: `/api/garden/${String(index).padStart(32, '0')}/snapshot`, source_kind: 'motion',
        motion_source: { ...motionSource, box_xywh: box } }));
    await mockGarden(page, { items: requested => (requested === 'pending' ? captures : []) });
    await openReview(page);
    await expect(page.locator('[data-garden-card]')).toHaveCount(1);
    await expect(page.locator('[data-garden-card-group]')).toHaveText('4 photos, same position');
    await openFirst(page);
    for (let index = 0; index < captures.length; index++) {
        await expect(record(page).locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${captures[index].id}/snapshot`));
        const peek = record(page).getByRole('button', { name: 'Show whole photo', exact: true });
            if (await peek.getAttribute('aria-pressed') !== 'true') await peek.click();
        await expect(record(page).locator('[data-garden-capture-box] rect').last()).toHaveAttribute('width', String(boxes[index][2] * 1280));
        await expect(record(page).getByText(`Photo ${index + 1} of 4`, { exact: true })).toBeVisible();
        if (index + 1 < captures.length) await nextPhoto(page);
    }
});

test('109 repeated proposals become two position groups with exact photo review and bounded dismissal', async ({ page }) => {
    const originals = Array.from({ length: 109 }, (_, index) => ({ ...row, id: index.toString(16).padStart(32, '0'),
        snapshot_url: `/api/garden/${index.toString(16).padStart(32, '0')}/snapshot`, source_kind: 'motion',
        observed_at: new Date(Date.UTC(2026, 9, 14, 1, 0, index)).toISOString(),
        motion_source: { ...motionSource, box_xywh: index === 108 ? [0.7, 0.1, 0.2, 0.2] : motionSource.box_xywh } }));
    let pending = [...originals];
    const writes: { ids: string[]; action: string }[] = [];
    await mockGarden(page, { items: requested => (requested === 'pending' ? pending : []) });
    await page.route('**/api/garden/review-batch', route => {
        const body = route.request().postDataJSON() as { ids: string[]; action: string };
        writes.push(body);
        pending = body.action === 'dismiss' ? pending.filter(item => !body.ids.includes(item.id)) : [...originals];
        return route.fulfill({ json: { updated_ids: body.ids, skipped_count: 0 } });
    });
    await openReview(page);
    await expect(page.locator('[data-garden-card]')).toHaveCount(2);
    await expect(page.locator('[data-explorer-count]')).toContainText('Garden entries: 2 · captures: 109');
    // Page size now counts server groups, keeping every stack whole.
    await expect(page.locator('#page-size-selector')).toBeVisible();
    await openFirst(page);
    await expect(record(page).getByText('108 photos around the same position')).toBeVisible();
    await expect(record(page).getByText('Position does not identify an animal. This group can contain different visitors.')).toBeVisible();
    await nextPhoto(page);
    await expect(record(page).locator('[data-garden-capture-photo]')).toHaveAttribute('src', /00000000000000000000000000000001\/snapshot/);
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
    await fitsNarrowScreen(page);
    await record(page).getByRole('button', { name: 'Dismiss remaining 108 photos', exact: true }).click();
    expect(writes[0]).toEqual({ action: 'dismiss', ids: originals.slice(0, 108).map(item => item.id) });
    await expect(record(page)).toHaveCount(0);
    await wideAgain(page);
    await expect(page.locator('[data-garden-card]')).toHaveCount(1);
    await page.getByRole('button', { name: 'Undo group dismissal', exact: true }).click();
    await expect(page.locator('[data-garden-card]')).toHaveCount(2);
    expect(writes[1]).toEqual({ action: 'restore', ids: writes[0].ids });
});

for (const concurrentReview of [false, true]) {
    for (const keptIndex of [0, 1]) {
        test(`scan an 80-photo stack, keep photo ${keptIndex + 1} and dismiss the rest${concurrentReview ? ' with another owner review and a new capture' : ''}`, async ({ page }) => {
            const captures = Array.from({ length: 81 }, (_, index) => ({ ...row,
                id: index.toString(16).padStart(32, '0'),
                snapshot_url: `/api/garden/${index.toString(16).padStart(32, '0')}/snapshot`,
                source_kind: 'motion', motion_source: { ...motionSource, box_xywh: index === 80 ? [0.7, 0.1, 0.2, 0.2] : motionSource.box_xywh }
            }));
            const states = new Map(captures.map(item => [item.id, 'pending']));
            const writes: { ids: string[]; action: string }[] = [];
            const animalId = captures[keptIndex].id;
            const concurrentId = captures[keptIndex + 1].id;
            let confirmed = false;
            await mockGarden(page, { items: requested => captures.filter(item => states.get(item.id) === requested).map(item => ({ ...item, status: requested })) });
            await page.route('**/api/garden/*/confirm', route => {
                const reviewed = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
                states.set(reviewed, 'confirmed');
                confirmed = true;
                return route.fulfill({ json: { ...captures.find(item => item.id === reviewed), status: 'confirmed' } });
            });
            await page.route('**/api/garden/review-batch', route => {
                const body = route.request().postDataJSON() as { ids: string[]; action: string };
                writes.push(body);
                if (concurrentReview && body.action === 'dismiss') {
                    states.set(concurrentId, 'confirmed');
                    const fresh = 'f'.repeat(32);
                    captures.push({ ...captures[0], id: fresh, snapshot_url: `/api/garden/${fresh}/snapshot` });
                    states.set(fresh, 'pending');
                }
                const updated = body.ids.filter(item => states.get(item) === (body.action === 'dismiss' ? 'pending' : 'dismissed'));
                for (const item of updated) states.set(item, body.action === 'dismiss' ? 'dismissed' : 'pending');
                return route.fulfill({ json: { updated_ids: updated, skipped_count: body.ids.length - updated.length } });
            });
            await openReview(page);
            await openFirst(page);
            await expect(record(page).getByRole('button', { name: 'Dismiss remaining 80 photos', exact: true })).toBeVisible();
            if (keptIndex > 0) await nextPhoto(page);
            await expect(record(page).locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${animalId}/snapshot`));
            // A review refreshes the open stack in the background. Confirming the photo a stack is named
            // after renames the stack, so wait for that refresh rather than racing it to the next click.
            const stackRefreshed = page.waitForResponse(response => confirmed && /^\/api\/garden\/visits\/[^/]+\/captures$/.test(new URL(response.url()).pathname));
            await record(page).getByRole('button', { name: 'Confirm animal manually', exact: true }).click();
            await stackRefreshed;
            await expect(record(page).locator('[data-garden-capture-group] [role="group"]')).toHaveAttribute('aria-busy', 'false');
            await expect(record(page).locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${captures[keptIndex + 1].id}/snapshot`));
            await expect(record(page).getByText(`Photo ${keptIndex + 1} of 79`, { exact: true })).toBeVisible();
            await record(page).getByRole('button', { name: 'Dismiss remaining 79 photos', exact: true }).click();
            await expect(toasts(page)).toContainText(`${concurrentReview ? 78 : 79} photos dismissed.`);
            expect(writes[0]).toEqual({ action: 'dismiss', ids: captures.slice(0, 80).filter(item => item.id !== animalId).map(item => item.id) });
            expect(states.get(animalId)).toBe('confirmed');
            expect(states.get(captures[80].id)).toBe('pending');
            if (concurrentReview) {
                expect(states.get(concurrentId)).toBe('confirmed');
                expect(states.get('f'.repeat(32))).toBe('pending');
                await expect(toasts(page)).toContainText('1 photos were unchanged');
            }
            await page.getByRole('button', { name: 'Undo group dismissal', exact: true }).click();
            await expect(toasts(page)).toContainText(`${concurrentReview ? 78 : 79} photos returned to review.`);
            expect(writes[1].ids).not.toContain(animalId);
            if (concurrentReview) expect(writes[1].ids).not.toContain(concurrentId);
            expect(states.get(animalId)).toBe('confirmed');
            await chooseReview(page, 'confirmed');
            // Two confirmed animals on one camera at the same moment are one visit, as birds are.
            await expect(page.locator('[data-garden-card]')).toHaveCount(1);
            if (concurrentReview) await expect(page.locator('[data-garden-card-group]')).toHaveText('2 captures in this visit');
            await openFirst(page);
            const photos = record(page).locator('[data-garden-capture-photo]');
            if (concurrentReview && !(await photos.getAttribute('src'))?.includes(animalId)) {
                await nextPhoto(page);
            }
            await expect(photos).toHaveAttribute('src', new RegExp(`${animalId}/snapshot`));
        });
    }
}

test('a failed stack dismissal keeps its photos reviewable and does not offer a false Undo', async ({ page }) => {
    const captures = [row.id, 'b'.repeat(32)].map(item => ({ ...row, id: item, snapshot_url: `/api/garden/${item}/snapshot`, source_kind: 'motion', motion_source: motionSource }));
    await mockGarden(page, { items: requested => (requested === 'pending' ? captures : []) });
    await page.route('**/api/garden/review-batch', route => route.fulfill({ status: 503, json: { detail: 'Stack review temporarily unavailable.' } }));
    await openReview(page);
    await openFirst(page);
    await record(page).getByRole('button', { name: 'Dismiss remaining 2 photos', exact: true }).click();
    await expect(toasts(page)).toContainText('Stack review temporarily unavailable.');
    await expect(toasts(page)).not.toContainText('photos dismissed.');
    await expect(record(page).getByRole('button', { name: 'Dismiss remaining 2 photos', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Undo group dismissal', exact: true })).toHaveCount(0);
    await expect(record(page).getByText('2 photos around the same position', { exact: true })).toBeVisible();
});

for (const action of ['confirm', 'dismiss'] as const) {
    test(`${action} visibly saves only the displayed photo while similar photos remain`, async ({ page }) => {
        const second = 'b'.repeat(32);
        const captures = [row.id, second].map(item => ({ ...row, id: item, snapshot_url: `/api/garden/${item}/snapshot`, source_kind: 'motion', motion_source: motionSource }));
        const writes: string[] = [];
        await mockGarden(page, { items: requested => (requested === 'pending' ? captures : []) });
        await page.route(`**/api/garden/*/${action}`, route => {
            const reviewed = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
            writes.push(reviewed);
            const index = captures.findIndex(item => item.id === reviewed);
            const original = captures[index];
            captures.splice(index, 1);
            return route.fulfill({ json: { ...original, status: action === 'confirm' ? 'confirmed' : 'dismissed' } });
        });
        await openReview(page);
        await openFirst(page);
        await nextPhoto(page);
        await record(page).getByRole('button', { name: action === 'confirm' ? 'Confirm animal manually' : 'Dismiss capture', exact: true }).click();
        await expect(toasts(page)).toContainText(action === 'confirm' ? 'Photo confirmed.' : 'Capture dismissed.');
        await expect(toasts(page)).toContainText('Other photos in this group still need review.');
        await expect(record(page).locator('[data-garden-capture-photo]')).toHaveAttribute('src', new RegExp(`${row.id}/snapshot`));
        await expect(page.locator('[data-explorer-count]')).toContainText('Garden entries: 1 · captures: 1');
        expect(writes).toEqual([second]);
        await fitsNarrowScreen(page);
    });
}

test('failed review stays pending and never announces success', async ({ page }) => {
    await mockGarden(page, { items: requested => (requested === 'pending' ? [row] : []) });
    await page.route('**/api/garden/*/dismiss', route => route.fulfill({ status: 503, json: { detail: 'Review temporarily unavailable.' } }));
    await openReview(page);
    await openFirst(page);
    await record(page).getByRole('button', { name: 'Dismiss capture', exact: true }).click();
    await expect(record(page).getByRole('alert')).toContainText('Review temporarily unavailable.');
    await expect(toasts(page)).toContainText('Review temporarily unavailable.');
    await expect(toasts(page)).not.toContainText('Capture dismissed.');
    await expect(record(page).getByRole('button', { name: 'Dismiss capture', exact: true })).toBeEnabled();
    await expect(page.locator('[data-garden-card]')).toHaveCount(1);
});

test('confirmation in a position group applies only to the displayed original photo', async ({ page }) => {
    const second = 'b'.repeat(32);
    const captures = [row.id, second].map(item => ({ ...row, id: item, snapshot_url: `/api/garden/${item}/snapshot`, source_kind: 'motion', motion_source: motionSource }));
    const confirmed: string[] = [];
    await mockGarden(page, { items: requested => (requested === 'pending' ? captures : []) });
    await page.route('**/api/garden/*/confirm', route => {
        confirmed.push(new URL(route.request().url()).pathname.split('/').at(-2) ?? '');
        return route.fulfill({ json: { ...captures[1], status: 'confirmed' } });
    });
    await openReview(page);
    await openFirst(page);
    await nextPhoto(page);
    await record(page).getByRole('button', { name: 'Confirm animal manually', exact: true }).click();
    expect(confirmed).toEqual([second]);
});

test('an old Garden page link with the beta off says so instead of silently showing birds', async ({ page }) => {
    await mockGarden(page, { items: () => [] });
    await page.goto('/browser-tests/owner-history.html?surface=explorer&garden=0&visitors=garden&review=pending');
    await expect(page.locator('[data-garden-beta-off]')).toBeVisible();
    await expect(page.locator('[data-explorer-visitors-facet]')).toHaveCount(0);
});

test("one animal's repeated captures are one Explorer entry, as a bird's visit is", async ({ page }) => {
    const named = { outcome: 'suggestion', reason: 'garden', review: 'accepted', automatic: true, name: 'Red fox', rank: 'species', score: 0.93, country: 'GBR', variant: '4.0.3a', provider: 'cpu', devices: ['CPU'], output_index: 1, input_kind: 'whole_image', frame_size: [1280, 720], identified_at: '2026-10-24T07:00:00Z' };
    // Twenty captures ten seconds apart, then the fox returns after five quiet minutes.
    const stay = Array.from({ length: 20 }, (_, index) => ({ ...row, id: `f${index}`.padStart(32, '0'), status: 'confirmed', identification: named,
        observed_at: new Date(Date.UTC(2026, 9, 24, 7, 10, 0) - index * 10_000).toISOString(), snapshot_url: `/api/garden/f${index}/snapshot` }));
    const later = { ...stay[0], id: 'g'.repeat(32), observed_at: '2026-10-24T07:15:30.000Z', snapshot_url: '/api/garden/g/snapshot' };
    await mockGarden(page, { items: requested => (requested === 'confirmed' ? [later, ...stay] : []) });
    await openReview(page, 'confirmed');
    await expect(page.locator('[data-garden-card]')).toHaveCount(2);
    await expect(page.locator('[data-explorer-count]')).toContainText('Garden entries: 2 · captures: 21');
    const visit = page.locator('[data-garden-card]').filter({ has: page.locator('[data-garden-card-group]') });
    await expect(visit.locator('[data-garden-card-group]')).toHaveText('20 captures in this visit');
    await visit.getByRole('button', { name: /^Open Garden capture/ }).click();
    await expect(record(page).getByText('20 captures in this visit', { exact: true })).toBeVisible();
    await expect(record(page).getByText('Photo 1 of 20', { exact: true })).toBeVisible();
    await nextPhoto(page);
    await expect(record(page).getByText('Photo 2 of 20', { exact: true })).toBeVisible();
    // The pending-only stack action stays separate from explicit visit dismissal.
    await expect(record(page).getByRole('button', { name: /^Dismiss remaining/ })).toHaveCount(0);
});


test('a 215-photo visit stays on one group page and its photo navigation crosses capture pages', async ({ page }) => {
    test.setTimeout(90_000);
    const photos = Array.from({ length: 215 }, (_, index) => ({ ...row,
        id: `long-${String(index).padStart(3, '0')}`.padEnd(32, '0'), status: 'confirmed',
        observed_at: new Date(Date.UTC(2026, 9, 24, 7, 0, 214-index)).toISOString(),
        snapshot_url: `/api/garden/long-${index}/snapshot` }));
    const other = Array.from({ length: 24 }, (_, index) => ({ ...row,
        id: `separate-${String(index).padStart(3, '0')}`.padEnd(32, '0'), status: 'confirmed', camera: `camera-${index}`,
        observed_at: new Date(Date.UTC(2026, 9, 24, 6, index)).toISOString() }));
    await mockGarden(page, { items: () => [...photos, ...other] });
    const reads: number[] = [];
    page.on('request', request => {
        const url = new URL(request.url());
        if (url.pathname.startsWith('/api/garden/visits/') && url.pathname.endsWith('/captures')) reads.push(Number(url.searchParams.get('offset')));
    });
    await openReview(page, 'confirmed');
    await expect(page.locator('[data-garden-card]')).toHaveCount(24);
    await expect(page.locator('[data-explorer-count]')).toContainText('Garden entries: 25 · captures: 239');
    await expect(page.locator('[data-garden-card-group]').first()).toContainText('215 captures');
    await openFirst(page);
    await expect(record(page).getByText('Photo 1 of 215', { exact: true })).toBeVisible();
    await expect(record(page).getByRole('button', { name: 'Dismiss 215 captures in this visit' })).toBeDisabled();
    await expect(record(page).getByText('Visits with more than 128 captures must be dismissed one capture at a time.', { exact: true })).toBeVisible();
    await record(page).locator('[data-garden-capture-choice]').last().click();
    await record(page).getByRole('button', { name: 'More photos', exact: true }).click();
    await expect(record(page).getByText('Photo 129 of 215', { exact: true })).toBeVisible();
    await expect(record(page).locator('[data-garden-capture-photo]')).toHaveAttribute('src', /long-128\/snapshot/);
    await record(page).getByRole('button', { name: 'Previous photos', exact: true }).click();
    await expect(record(page).getByText('Photo 128 of 215', { exact: true })).toBeVisible();
    expect(reads).toEqual([0, 128, 0]);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Next page', exact: true }).click();
    await expect(page.locator('[data-garden-card]')).toHaveCount(1);
    await expect(page.locator('[data-garden-card-group]')).toHaveCount(0);
});

test('a late capture-page read cannot undo the displayed owner confirmation', async ({ page }) => {
    let current = { ...row };
    await mockGarden(page, { items: () => [current] });
    let release = () => {};
    const gate = new Promise<void>(resolve => { release = resolve; });
    await page.route('**/api/garden/visits/*/captures?**', async route => {
        const stale = { ...current };
        await gate;
        return route.fulfill({ json: { items: [stale], total: 1, limit: 128, offset: 0 } });
    });
    await page.route('**/api/garden/*/confirm', route => {
        current = { ...current, status: 'confirmed' };
        return route.fulfill({ json: current });
    });
    await page.goto('/browser-tests/owner-history.html?surface=explorer&garden=1&visitors=garden');
    await openFirst(page);
    await record(page).getByRole('button', { name: 'Confirm animal manually' }).click();
    await expect(record(page).locator('[data-garden-capture-status]')).toHaveAttribute('data-garden-capture-status', 'confirmed');
    const loaded = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/captures'));
    release();
    await loaded;
    await expect(record(page).locator('[data-garden-capture-status]')).toHaveAttribute('data-garden-capture-status', 'confirmed');
    await expect(record(page).getByText('Waiting for automatic identification', { exact: true })).toHaveCount(0);
});

test('confirming one photo in the mixed review state leaves its pending position stack', async ({ page }) => {
    const pending = [row, { ...row, id: 'b'.repeat(32), snapshot_url: `/api/garden/${'b'.repeat(32)}/snapshot` }]
        .map(item => ({ ...item, source_kind: 'motion', motion_source: motionSource }));
    const confirmed: Capture[] = [];
    await mockGarden(page, { items: () => [...pending, ...confirmed] });
    await page.route('**/api/garden/*/confirm', route => {
        const id = new URL(route.request().url()).pathname.split('/').at(-2);
        const at = pending.findIndex(item => item.id === id);
        const reviewed = { ...pending[at], status: 'confirmed' };
        pending.splice(at, 1);
        confirmed.push(reviewed);
        return route.fulfill({ json: reviewed });
    });
    await page.goto('/browser-tests/owner-history.html?surface=explorer&garden=1&visitors=garden');
    await openFirst(page);
    await expect(record(page).locator('[data-garden-capture-choice]')).toHaveCount(2);
    await expect(record(page).locator('[data-garden-capture-choice]').nth(1)).toBeEnabled();
    await record(page).getByRole('button', { name: 'Confirm animal manually' }).click();
    await expect(record(page).locator('[data-garden-capture-status]')).toHaveAttribute('data-garden-capture-status', 'confirmed');
    await expect(record(page).locator('[data-garden-capture-choice]')).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-garden-card="confirmed"]')).toHaveCount(1);
    await expect(page.locator('[data-garden-card="pending"]')).toHaveCount(1);
});
