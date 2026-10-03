import { test, expect, type Page, type Route } from '@playwright/test';

// Boundary fixture: the actual review queue and detection record, with /api mocked here.
// Every image is a synthetic SVG with a declared pixel size, so geometry can be checked.
// This proves rendering and state handling against missing, late and stale media; it is not
// backend, cache or inference E2E. Mutations only ever reach these fixture routes.

type Capture = 'tit' | 'robin' | 'wren';

const FULL = { width: 2560, height: 1440 };
const CROP = { width: 259, height: 172 };
const TIT_CHOSEN_CROP = [1701, 1001, 1960, 1173];

function svg(width: number, height: number, fill: string, label: string): string {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`
        + `<rect width="${width}" height="${height}" fill="${fill}"/>`
        + `<text x="50%" y="50%" fill="#f8fafc" font-family="sans-serif" font-size="${Math.round(height / 6)}" text-anchor="middle">${label}</text></svg>`;
}

interface CandidateSpec {
    id: string;
    mode: 'frigate_hint_crop' | 'model_crop' | 'full_frame';
    frame: number;
    clip: string;
    box: number[] | null;
    label: string;
    score: number;
    offset?: number | null;
}

const CANDIDATES: Record<Capture, CandidateSpec[]> = {
    // The reporter's capture: three framings of one Frigate snapshot frame, the hint crop chosen.
    tit: [
        { id: 'hint', mode: 'frigate_hint_crop', frame: 0, clip: 'frigate_snapshot', box: TIT_CHOSEN_CROP, label: 'Cyanistes caeruleus', score: 0.84 },
        { id: 'model', mode: 'model_crop', frame: 0, clip: 'frigate_snapshot', box: [1738, 1004, 1922, 1164], label: 'Cyanistes caeruleus', score: 0.83 },
        { id: 'full', mode: 'full_frame', frame: 0, clip: 'frigate_snapshot', box: null, label: 'Poecile gambeli', score: 0.03 }
    ],
    robin: [
        { id: 'model', mode: 'model_crop', frame: 0, clip: 'frigate_snapshot', box: [900, 500, 1200, 760], label: 'Erithacus rubecula', score: 0.7 },
        { id: 'full', mode: 'full_frame', frame: 0, clip: 'frigate_snapshot', box: null, label: 'Erithacus rubecula', score: 0.2 }
    ],
    // Two moments of one visit; the later one is the photograph.
    wren: [
        { id: 'f10-model', mode: 'model_crop', frame: 10, clip: 'event', box: [400, 300, 700, 560], label: 'Troglodytes troglodytes', score: 0.61, offset: 0.4 },
        { id: 'f10-full', mode: 'full_frame', frame: 10, clip: 'event', box: null, label: 'Troglodytes troglodytes', score: 0.2, offset: 0.4 },
        { id: 'f40-model', mode: 'model_crop', frame: 40, clip: 'event', box: [1500, 800, 1800, 1060], label: 'Troglodytes troglodytes', score: 0.72, offset: 1.6 },
        { id: 'f40-full', mode: 'full_frame', frame: 40, clip: 'event', box: null, label: 'Troglodytes troglodytes', score: 0.2, offset: 1.6 }
    ]
};

const INITIAL_SELECTION: Record<Capture, string> = { tit: 'hint', robin: 'model', wren: 'f40-model' };

function candidateUrl(capture: string, id: string, kind: 'image' | 'thumbnail'): string {
    return `/api/frigate/${capture}/snapshot/candidates/${capture}__${id}/${kind}.jpg?v=1`;
}

interface Plan {
    candidateMediaAbsent?: boolean;
    /** Photographs a later run replaced, kept as the backend keeps them: no frame, no time, no read. */
    retainedPhotos?: string[];
    fullSize?: { width: number; height: number };
    /** Path fragments that answer 404. */
    missing: string[];
    /** Path fragments held until the test releases them. */
    held: Map<string, Promise<void>>;
    /** Candidate list reads held until released, per capture. */
    heldLists: Map<string, Promise<void>>;
    selection: Record<string, string>;
    requests: string[];
    errors: string[];
}

function newPlan(): Plan {
    return { missing: [], held: new Map(), heldLists: new Map(), selection: { ...INITIAL_SELECTION }, requests: [], errors: [] };
}

function gate(): { promise: Promise<void>; release: () => void } {
    let release: () => void = () => undefined;
    const promise = new Promise<void>((resolve) => { release = resolve; });
    return { promise, release };
}

function candidateList(capture: Capture, plan: Plan) {
    const chosen = plan.selection[capture];
    const candidates: Record<string, unknown>[] = CANDIDATES[capture].map((spec) => ({
        candidate_id: `${capture}__${spec.id}`,
        frame_index: spec.frame,
        frame_offset_seconds: spec.offset ?? null,
        source_mode: spec.mode,
        clip_variant: spec.clip,
        crop_box: spec.box,
        crop_confidence: spec.mode === 'model_crop' ? 0.7 : null,
        classifier_label: spec.label,
        classifier_score: spec.score,
        ranking_score: spec.score,
        selected: spec.id === chosen,
        snapshot_source: `hq_candidate_${spec.mode}`,
        image_url: plan.candidateMediaAbsent ? null : candidateUrl(capture, spec.id, 'image'),
        thumbnail_url: plan.candidateMediaAbsent ? null : candidateUrl(capture, spec.id, 'thumbnail')
    }));
    for (const digest of plan.retainedPhotos ?? []) {
        const id = `retained_snapshot__${digest}`;
        candidates.push({
            candidate_id: `${capture}__${id}`,
            frame_index: 0,
            frame_offset_seconds: null,
            source_mode: 'retained_photo',
            clip_variant: 'retained_snapshot',
            crop_box: null,
            crop_confidence: null,
            classifier_label: null,
            classifier_score: null,
            ranking_score: 0,
            selected: id === chosen,
            snapshot_source: 'frigate_snapshot_cropped',
            image_url: candidateUrl(capture, id, 'image'),
            thumbnail_url: candidateUrl(capture, id, 'thumbnail')
        });
    }
    const chosenSpec = CANDIDATES[capture].find((spec) => spec.id === chosen);
    const birds = capture === 'tit'
        ? [{
            id: 474, bird_index: 0, candidate_id: 'tit__model', clip_variant: 'frigate_snapshot', frame_index: 0,
            crop_box: [1756, 1041, 1904, 1128], detector_confidence: 0.71, species: 'Cyanistes caeruleus',
            classifier_label: 'Cyanistes caeruleus', classifier_score: 0.83, manual_species: false, is_hidden: false, is_unknown: false
        }]
        : [];
    return {
        event_id: capture,
        current_source: `hq_candidate_${chosenSpec?.mode ?? 'model_crop'}`,
        current_candidate_id: `${capture}__${chosen}`,
        candidates,
        birds
    };
}

function imageFor(path: string, plan: Plan): string {
    if (path.includes('/snapshot/candidates/')) {
        const full = path.includes('__full') || /__f\d+-full/.test(path);
        if (path.endsWith('thumbnail.jpg')) return svg(96, 64, full ? '#1e3a8a' : '#0f766e', full ? 'scene' : 'crop');
        const fullSize = plan.fullSize ?? FULL;
        return full ? svg(fullSize.width, fullSize.height, '#1e3a8a', 'whole scene') : svg(CROP.width, CROP.height, '#0f766e', 'crop');
    }
    if (path.endsWith('/snapshot.jpg')) return svg(CROP.width, CROP.height, '#7c2d12', 'saved photo');
    if (path.endsWith('/thumbnail.jpg')) return svg(175, 175, '#4c1d95', 'thumb');
    return svg(64, 64, '#334155', '');
}

async function serve(page: Page, plan: Plan): Promise<void> {
    // Isolate media layout from the external font service. The real application
    // and its chosen fonts are checked separately against Quark.
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    // WebKit reports a ResizeObserver that settled over two frames as a page error; it is a
    // browser notice, not a failure of the code under test.
    page.on('pageerror', (error) => {
        if (!error.message.includes('ResizeObserver loop')) plan.errors.push(error.message);
    });
    await page.route((url) => url.pathname.startsWith('/api/'), async (route: Route) => {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;
        plan.requests.push(`${request.method()} ${path}${url.search}`);

        const list = /^\/api\/frigate\/(tit|robin|wren)\/snapshot\/candidates$/.exec(path);
        if (list) {
            const held = plan.heldLists.get(list[1]);
            // Each read answers with the selection as it stands when it is released, the way a
            // slow server would.
            if (held) await held;
            return route.fulfill({ json: candidateList(list[1] as Capture, plan) }).catch(() => undefined);
        }
        const apply = /^\/api\/frigate\/(tit|robin|wren)\/snapshot\/apply$/.exec(path);
        if (apply && request.method() === 'POST') {
            const body = request.postDataJSON() as { candidate_id?: string };
            plan.selection[apply[1]] = (body.candidate_id ?? '').replace(`${apply[1]}__`, '');
            return route.fulfill({ json: { status: 'ok' } });
        }
        if (path.endsWith('.jpg') || path.endsWith('.svg')) {
            const heldKey = [...plan.held.keys()].find((key) => path.includes(key));
            if (heldKey) await plan.held.get(heldKey);
            if (plan.missing.some((fragment) => path.includes(fragment))) {
                return route.fulfill({ status: 404, body: '' }).catch(() => undefined);
            }
            return route.fulfill({ contentType: 'image/svg+xml', body: imageFor(path, plan) }).catch(() => undefined);
        }
        if (path.endsWith('/snapshot/status')) {
            return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'hq_candidate_model_crop' } });
        }
        if (path === '/api/species/search') {
            return route.fulfill({ json: [
                { id: 'Eurasian Blue Tit', display_name: 'Eurasian Blue Tit', common_name: 'Eurasian Blue Tit', scientific_name: 'Cyanistes caeruleus' },
                { id: 'European Robin', display_name: 'European Robin', common_name: 'European Robin', scientific_name: 'Erithacus rubecula' }
            ] });
        }
        if (path.startsWith('/api/audio/context/') || path.includes('/conversation') || path.endsWith('/species')) {
            return route.fulfill({ json: [] });
        }
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
}

async function openQueue(page: Page, plan: Plan, query = ''): Promise<void> {
    await serve(page, plan);
    await page.goto(`/browser-tests/review-media.html?surface=queue${query}`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-review-species-heading]')).toBeVisible();
}

async function openRecord(page: Page, plan: Plan, query = ''): Promise<void> {
    await serve(page, plan);
    await page.goto(`/browser-tests/review-media.html?surface=record${query}`, { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-detection-photograph]')).toBeVisible();
}

async function headingTop(page: Page): Promise<number> {
    const box = await page.locator('[data-review-species-heading]').boundingBox();
    if (!box) throw new Error('Species heading is not laid out');
    return Math.round(box.y);
}

interface ImageReport { src: string; loaded: boolean; broken: boolean; width: number; height: number }

/** Every image a container draws, and whether each one is a picture or a broken request. */
async function images(page: Page, selector: string): Promise<ImageReport[]> {
    return page.locator(selector).first().evaluate((root) =>
        [...root.querySelectorAll('img')]
            .filter((image) => image.getBoundingClientRect().width > 0 && getComputedStyle(image).visibility !== 'hidden')
            .map((image) => ({
                src: image.getAttribute('src') ?? '',
                loaded: image.complete && image.naturalWidth > 0,
                broken: image.complete && image.naturalWidth === 0,
                width: image.getBoundingClientRect().width,
                height: image.getBoundingClientRect().height
            })));
}

/** The queue's photograph: the slot directly above the species heading. */
async function queuePhoto(page: Page): Promise<{ images: ImageReport[]; placeholder: boolean; height: number }> {
    return page.locator('[data-review-species-heading]').evaluate((heading) => {
        const slot = heading.previousElementSibling as HTMLElement | null;
        if (!slot) return { images: [], placeholder: true, height: 0 };
        const shown = [...slot.querySelectorAll('img')]
            .filter((image) => image.getBoundingClientRect().width > 0 && getComputedStyle(image).opacity !== '0')
            .map((image) => ({
                src: image.getAttribute('src') ?? '',
                loaded: image.complete && image.naturalWidth > 0,
                broken: image.complete && image.naturalWidth === 0,
                width: image.getBoundingClientRect().width,
                height: image.getBoundingClientRect().height
            }));
        return { images: shown, placeholder: shown.length === 0, height: Math.round(slot.getBoundingClientRect().height) };
    });
}

async function settle(page: Page): Promise<void> {
    await page.evaluate(() => new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    await page.waitForTimeout(120);
}

test.describe('Needs your call keeps the photograph it already has', () => {
    test('skip shortcut works from initial button focus, but not while typing or with modifiers', async ({ page }) => {
        const plan = newPlan();
        await openQueue(page, plan);
        const heading = page.locator('[data-review-species-heading] h3');
        const close = page.getByRole('button', { name: 'Close', exact: true });
        await expect(close).toBeFocused();
        await close.dispatchEvent('keydown', { key: 's', ctrlKey: true });
        await expect(heading).toHaveText('Eurasian Blue Tit');
        const search = page.getByRole('searchbox', { name: 'Search species', exact: true });
        await search.focus();
        await page.keyboard.type('s');
        await expect(heading).toHaveText('Eurasian Blue Tit');
        await close.focus();
        await page.keyboard.press('s');
        await expect(heading).toHaveText('European Robin');
        expect(plan.errors).toEqual([]);
    });

    for (const surface of ['queue', 'record'] as const) {
        test(`${surface}: absent candidate URLs retain only the chosen frame and its saved photograph`, async ({ page }) => {
            const plan = newPlan();
            plan.candidateMediaAbsent = true;
            const list = gate();
            plan.heldLists.set('tit', list.promise);
            if (surface === 'queue') await openQueue(page, plan);
            else await openRecord(page, plan);
            const strip = page.locator('[data-frame-strip]');
            await expect(strip.locator('[data-frame-strip-pending]')).toBeVisible();
            const beforeHeight = await strip.evaluate(el => el.getBoundingClientRect().height);
            list.release();
            await expect(strip.getByRole('button', { name: /Compare frame/ })).toHaveCount(1);
            await expect.poll(async () => (await images(page, '[data-frame-strip]')).some(image => image.loaded)).toBe(true);
            const drawn = await images(page, '[data-frame-strip]');
            expect(drawn[0]?.src).toContain('/api/frigate/tit/snapshot.jpg');
            await settle(page);
            expect(await strip.evaluate(el => el.getBoundingClientRect().height)).toBeCloseTo(beforeHeight, 1);
            expect(plan.requests.some(request => request.includes('/snapshot/candidates/tit__'))).toBe(false);
            await expect(page.locator('[data-counted-birds]')).toHaveCount(1);
            expect(plan.errors).toEqual([]);
        });
    }
    test('a candidate list advertising missing files does not replace the saved photograph (#reporter Blue Tit)', async ({ page }, testInfo) => {
        const plan = newPlan();
        const list = gate();
        plan.heldLists.set('tit', list.promise);
        // The reporter's capture: every candidate file is gone; the saved photograph is not.
        plan.missing.push('/api/frigate/tit/snapshot/candidates/');
        await openQueue(page, plan);

        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded)).toBe(true);
        const before = await queuePhoto(page);
        const topBefore = await headingTop(page);
        await page.screenshot({ path: testInfo.outputPath('tit-before-candidates.png') });

        list.release();
        await expect.poll(() => plan.requests.some((request) => request.includes('/snapshot/candidates/tit__'))).toBe(true);
        await settle(page);

        const after = await queuePhoto(page);
        await page.screenshot({ path: testInfo.outputPath('tit-after-candidates.png'), fullPage: true });
        expect(after.placeholder, 'the photograph became a placeholder').toBe(false);
        expect(after.images.every((image) => image.loaded), JSON.stringify(after.images)).toBe(true);
        // The saved photograph is the chosen one; candidate metadata does not swap it out.
        expect(after.images[0]?.src).toContain('/api/frigate/tit/snapshot.jpg');
        expect(after.height).toBe(before.height);
        expect(await headingTop(page)).toBe(topBefore);
        expect(plan.errors).toEqual([]);
    });

    test('the photograph slot keeps one size while loading, loaded and with every image missing', async ({ page }, testInfo) => {
        const plan = newPlan();
        const snapshot = gate();
        plan.held.set('/api/frigate/tit/snapshot.jpg', snapshot.promise);
        plan.held.set('/api/frigate/tit/thumbnail.jpg', snapshot.promise);
        await openQueue(page, plan);
        await settle(page);
        const loadingTop = await headingTop(page);
        const loadingHeight = (await queuePhoto(page)).height;

        snapshot.release();
        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded)).toBe(true);
        await settle(page);
        expect(await headingTop(page), 'the heading moved when the photograph arrived').toBe(loadingTop);
        expect((await queuePhoto(page)).height).toBe(loadingHeight);

        // Same capture, nothing retrievable at all.
        const missing = newPlan();
        missing.missing.push('/api/frigate/tit/');
        await page.unrouteAll({ behavior: 'ignoreErrors' });
        await openQueue(page, missing);
        await expect.poll(() => missing.requests.some((request) => request.includes('/snapshot/candidates/tit__'))).toBe(true);
        await settle(page);
        const failed = await queuePhoto(page);
        await page.screenshot({ path: testInfo.outputPath('tit-all-missing.png'), fullPage: true });
        expect(failed.images.filter((image) => image.broken), 'a broken image is drawn').toEqual([]);
        expect(failed.height, 'a failed photograph is a different size').toBe(loadingHeight);
        expect(await headingTop(page)).toBe(loadingTop);
    });

    test('a late candidate list and a late image error from the previous capture cannot touch the next', async ({ page }) => {
        const plan = newPlan();
        const titList = gate();
        const titPhoto = gate();
        plan.heldLists.set('tit', titList.promise);
        plan.held.set('/api/frigate/tit/', titPhoto.promise);
        plan.missing.push('/api/frigate/tit/');
        await openQueue(page, plan);

        await page.getByRole('button', { name: 'Skip for now' }).click();
        await expect(page.locator('[data-review-species-heading] h3')).toHaveText('European Robin');
        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded)).toBe(true);
        const robin = await queuePhoto(page);
        const robinTop = await headingTop(page);

        titList.release();
        titPhoto.release();
        await settle(page);
        await page.waitForTimeout(200);

        await expect(page.locator('[data-review-species-heading] h3')).toHaveText('European Robin');
        const after = await queuePhoto(page);
        expect(after.images.map((image) => image.src)).toEqual(robin.images.map((image) => image.src));
        expect(after.images.every((image) => image.loaded)).toBe(true);
        expect(await headingTop(page)).toBe(robinTop);
        await expect(page.locator('[data-review-species-heading]')).not.toContainText('Cyanistes caeruleus');
        // The Blue Tit's counted bird never lands on the Robin.
        await expect(page.locator('[data-counted-birds]')).toHaveCount(0);
        expect(plan.errors).toEqual([]);
    });

    test('a whole scene that cannot load returns to the photograph instead of a placeholder', async ({ page }, testInfo) => {
        const plan = newPlan();
        plan.missing.push('/api/frigate/tit/snapshot/candidates/tit__full/image.jpg');
        await openQueue(page, plan);
        const peek = page.locator('[data-review-whole-scene-peek]');
        await expect(peek).toHaveCount(1);
        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded)).toBe(true);
        const before = await queuePhoto(page);

        await peek.focus();
        await expect.poll(() => plan.requests.some((request) => request.includes('tit__full/image.jpg'))).toBe(true);
        await settle(page);

        const after = await queuePhoto(page);
        await page.screenshot({ path: testInfo.outputPath('tit-peek-missing.png') });
        expect(after.placeholder, 'the photograph was given up for a missing whole scene').toBe(false);
        expect(after.images.filter((image) => image.broken)).toEqual([]);
        expect(after.images.some((image) => image.loaded && image.src.includes('/api/frigate/tit/snapshot.jpg'))).toBe(true);
        expect(after.height).toBe(before.height);
        // A whole scene that is not there is no longer offered, and no outline is drawn anywhere.
        await expect(peek).toHaveCount(0);
        await expect(page.locator('[data-review-other-bird-outline]')).toHaveCount(0);
        await expect(page.locator('[data-review-queue-modal]')).not.toContainText('Whole scene');
    });

    test('a whole scene that loads outlines the chosen crop on its own pixels', async ({ page }, testInfo) => {
        const plan = newPlan();
        await openQueue(page, plan);
        const peek = page.locator('[data-review-whole-scene-peek]');
        await expect(peek).toHaveCount(1);
        await peek.focus();
        const outline = page.locator('[data-review-whole-scene-outline]');
        await expect(outline).toBeVisible();
        await settle(page);

        const scene = await page.locator('[data-review-whole-scene-image]').evaluate((image) => {
            const element = image as HTMLImageElement;
            const rect = element.getBoundingClientRect();
            const scale = Math.min(rect.width / element.naturalWidth, rect.height / element.naturalHeight);
            return {
                left: rect.left + (rect.width - element.naturalWidth * scale) / 2,
                top: rect.top + (rect.height - element.naturalHeight * scale) / 2,
                scale
            };
        });
        const box = await outline.boundingBox();
        expect(box).toBeTruthy();
        const [left, top, right] = TIT_CHOSEN_CROP;
        expect(Math.abs(box!.x - (scene.left + left * scene.scale))).toBeLessThan(2);
        expect(Math.abs(box!.y - (scene.top + top * scene.scale))).toBeLessThan(2);
        expect(Math.abs(box!.width - (right - left) * scene.scale)).toBeLessThan(2);
        await page.screenshot({ path: testInfo.outputPath('tit-peek.png') });

        // Leaving returns to the saved photograph.
        await page.locator('[data-review-queue-modal] input[type="search"]').focus();
        await expect(outline).toHaveCount(0);
        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded && image.src.includes('/api/frigate/tit/snapshot.jpg'))).toBe(true);
    });
});

test.describe('the frame strip marks the photograph honestly', () => {
    test('one frame is not marked as chosen against nothing, and is not repeated beneath itself', async ({ page }) => {
        const plan = newPlan();
        await openQueue(page, plan);
        await expect.poll(() => plan.requests.some((request) => request.includes('/snapshot/candidates/tit__'))).toBe(true);
        await settle(page);
        await expect(page.locator('[data-review-queue-modal]').getByText('Chosen', { exact: true })).toHaveCount(0);
    });

    test('the chosen moment keeps a picture when its own thumbnail is missing, and choosing another moves the mark', async ({ page }, testInfo) => {
        const plan = newPlan();
        plan.missing.push('/api/frigate/wren/snapshot/candidates/wren__f40-model/');
        await openQueue(page, plan, '&queue=wren,robin');
        const triggers = page.locator('[data-frame-strip] button[aria-pressed]');
        await expect(triggers).toHaveCount(2);
        await expect(triggers.nth(1)).toHaveAttribute('aria-pressed', 'true');
        await expect(triggers.nth(0)).toHaveAttribute('aria-pressed', 'false');
        await settle(page);

        const chosen = await triggers.nth(1).evaluate((button) => [...button.querySelectorAll('img')].map((image) => ({
            src: image.getAttribute('src') ?? '', loaded: image.complete && image.naturalWidth > 0
        })));
        expect(chosen.some((image) => image.loaded), 'the chosen moment lost its picture').toBe(true);
        await expect(triggers.nth(1)).toContainText('Chosen');
        await expect(triggers.nth(0)).not.toContainText('Chosen');
        await page.screenshot({ path: testInfo.outputPath('wren-strip.png') });

        const firstSnapshotReads = plan.requests.filter((request) => request.startsWith('GET /api/frigate/wren/snapshot.jpg')).length;
        await triggers.nth(0).click();
        await page.getByRole('button', { name: 'Use this frame' }).click();
        await expect.poll(() => plan.requests.some((request) => request.startsWith('POST /api/frigate/wren/snapshot/apply'))).toBe(true);
        await expect(triggers.nth(0)).toHaveAttribute('aria-pressed', 'true');
        await expect(triggers.nth(1)).toHaveAttribute('aria-pressed', 'false');
        // The saved photograph changed on the server, so it is read again rather than served stale.
        await expect.poll(() => plan.requests.filter((request) => request.startsWith('GET /api/frigate/wren/snapshot.jpg')).length)
            .toBeGreaterThan(firstSnapshotReads);
        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded)).toBe(true);
    });

    test('each earlier photograph is its own option, named as one, with no frame time, and can be restored', async ({ page }, testInfo) => {
        const plan = newPlan();
        plan.retainedPhotos = ['a1b2c3d4e5f6', '0f9e8d7c6b5a'];
        await openQueue(page, plan, '&queue=wren,robin');
        const strip = page.locator('[data-frame-strip]');
        const triggers = strip.locator('button[aria-pressed]');
        await expect(triggers).toHaveCount(4);
        // Kept stills are not frames of the clip, so the strip counts photo options.
        await expect(strip).toContainText('4 photo options from this visit');
        await settle(page);
        await page.screenshot({ path: testInfo.outputPath('wren-earlier-photos-strip.png') });

        for (const index of [0, 1]) {
            await triggers.nth(index).click();
            const panel = page.locator('[data-frame-strip-panel]');
            await expect(panel).toContainText('An earlier photograph');
            await expect(panel).toContainText('before a later analysis replaced it');
            await expect(panel).not.toContainText('Frame ');
            await expect(panel).not.toContainText(/\d+:\d{2}/);
            await expect(panel.getByRole('button', { name: 'Use this photo' })).toBeVisible();
            if (index === 0) await page.screenshot({ path: testInfo.outputPath('wren-earlier-photo-panel.png') });
            await page.keyboard.press('Escape');
            await expect(panel).toHaveCount(0);
        }

        await triggers.nth(1).click();
        await page.getByRole('button', { name: 'Use this photo' }).click();
        await expect.poll(() => plan.selection.wren).toBe('retained_snapshot__0f9e8d7c6b5a');
        await expect(triggers.nth(1)).toHaveAttribute('aria-pressed', 'true');
        await expect(triggers.nth(0)).toHaveAttribute('aria-pressed', 'false');
        expect(plan.errors).toEqual([]);
    });

    test('the strip holds its row while its frames are read', async ({ page }) => {
        const plan = newPlan();
        const list = gate();
        plan.heldLists.set('wren', list.promise);
        await openQueue(page, plan, '&queue=wren');
        await settle(page);
        const strip = page.locator('[data-review-frame-strip]');
        await expect(strip, 'nothing holds the strip\'s place while it loads').toHaveCount(1);
        const loading = await strip.boundingBox();
        const topBefore = await headingTop(page);
        list.release();
        await expect(page.locator('[data-frame-strip] button[aria-pressed]')).toHaveCount(2);
        await settle(page);
        const loaded = await strip.boundingBox();
        expect(Math.abs((loaded?.height ?? 0) - (loading?.height ?? 0))).toBeLessThanOrEqual(1);
        expect(await headingTop(page)).toBe(topBefore);
    });
});

test.describe('the counted frame in the queue', () => {
    for (const size of [{ width: 2560, height: 1920 }, { width: 2560, height: 2560 }]) {
        test(`a ${size.width}x${size.height} counted frame arrives without moving its rows`, async ({ page }) => {
            const plan = newPlan();
            plan.fullSize = size;
            const image = gate();
            plan.held.set('/tit__full/image.jpg', image.promise);
            await openQueue(page, plan);
            const frame = page.locator('[data-counted-birds-frame]');
            await expect(frame).toHaveCount(1);
            await settle(page);
            const before = await frame.boundingBox();
            image.release();
            await expect.poll(() => frame.locator('img').evaluate(img => (img as HTMLImageElement).naturalHeight)).toBe(size.height);
            await settle(page);
            const after = await frame.boundingBox();
            expect(Math.abs((after?.height ?? 0) - (before?.height ?? 0))).toBeLessThanOrEqual(1);
            await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(1);
            const geometry = await frame.evaluate(element => {
                const image = element.querySelector('img');
                const outline = element.querySelector('[data-counted-bird-outline]');
                if (!image || !outline) throw new Error('Missing counted image or outline');
                const imageRect = image.getBoundingClientRect();
                const actual = outline.getBoundingClientRect();
                const scale = Math.min(imageRect.width / image.naturalWidth, imageRect.height / image.naturalHeight);
                return {
                    actual: [actual.left - imageRect.left, actual.top - imageRect.top, actual.width, actual.height],
                    expected: [
                        (imageRect.width - image.naturalWidth * scale) / 2 + 1756 * scale,
                        (imageRect.height - image.naturalHeight * scale) / 2 + 1041 * scale,
                        (1904 - 1756) * scale, (1128 - 1041) * scale
                    ]
                };
            });
            for (let index = 0; index < geometry.actual.length; index += 1) {
                expect(Math.abs(geometry.actual[index] - geometry.expected[index])).toBeLessThan(1);
            }
        });
    }
    test('a counted frame that cannot load keeps its place, draws no outline and comes after the decision', async ({ page }, testInfo) => {
        const plan = newPlan();
        plan.missing.push('/api/frigate/tit/snapshot/candidates/');
        await openQueue(page, plan);
        const section = page.locator('[data-counted-birds]');
        await expect(section).toBeVisible();
        await expect.poll(() => plan.requests.some((request) => request.includes('tit__full/image.jpg'))).toBe(true);
        await settle(page);

        await expect(page.locator('[data-counted-birds-frame]'), 'the counted frame was removed when it failed').toHaveCount(1);
        await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(0);
        await expect(section).toContainText('The counted frame did not load');
        await expect(section.locator('.border-dashed')).toHaveCount(0);
        expect((await images(page, '[data-counted-birds]')).filter((image) => image.broken)).toEqual([]);

        // The decision comes first on every screen size: the bird count is supporting detail.
        const order = await page.evaluate(() => {
            const decision = document.querySelector('[data-review-queue-modal] [data-review-reason]');
            const counted = document.querySelector('[data-counted-birds]');
            return decision && counted ? Boolean(decision.compareDocumentPosition(counted) & Node.DOCUMENT_POSITION_FOLLOWING) : null;
        });
        expect(order, 'the bird count sits before the decision').toBe(true);
        await page.screenshot({ path: testInfo.outputPath('tit-counted-missing.png'), fullPage: true });
    });
});

test.describe('the detection record degrades the same way', () => {
    test('a missing whole scene and missing candidates leave the saved photograph in place', async ({ page }, testInfo) => {
        const plan = newPlan();
        plan.missing.push('/api/frigate/tit/snapshot/candidates/');
        await openRecord(page, plan);
        await expect.poll(async () => (await images(page, '[data-detection-photograph]')).some((image) => image.loaded)).toBe(true);
        const peek = page.locator('[data-detection-whole-scene-peek]');
        if (await peek.count()) {
            await peek.focus();
            await expect.poll(() => plan.requests.some((request) => request.includes('tit__full/image.jpg'))).toBe(true);
        }
        await settle(page);
        const shown = await images(page, '[data-detection-photograph]');
        await page.screenshot({ path: testInfo.outputPath('record-candidates-missing.png') });
        expect(shown.filter((image) => image.broken), 'the record draws a broken image').toEqual([]);
        expect(shown.some((image) => image.loaded && image.src.includes('/api/frigate/tit/snapshot.jpg'))).toBe(true);
        await expect(peek).toHaveCount(0);
        await expect(page.locator('[data-detection-whole-scene-outline]')).toHaveCount(0);
    });

    test('with every image missing the record shows a placeholder, never a broken image', async ({ page }, testInfo) => {
        const plan = newPlan();
        plan.missing.push('/api/frigate/tit/');
        await openRecord(page, plan);
        await expect.poll(() => plan.requests.some((request) => request.includes('/api/frigate/tit/snapshot.jpg'))).toBe(true);
        await settle(page);
        const photograph = page.locator('[data-detection-photograph]');
        const before = await photograph.boundingBox();
        await page.waitForTimeout(200);
        const shown = await images(page, '[data-detection-photograph]');
        await page.screenshot({ path: testInfo.outputPath('record-all-missing.png') });
        expect(shown.filter((image) => image.broken), JSON.stringify(shown)).toEqual([]);
        await expect(photograph.locator('[data-media-placeholder]')).toHaveCount(1);
        expect((await photograph.boundingBox())?.height).toBe(before?.height);
    });

    test('the record\'s strip holds its row while its frames are read', async ({ page }) => {
        const plan = newPlan();
        const list = gate();
        plan.heldLists.set('wren', list.promise);
        await openRecord(page, plan, '&queue=wren');
        const picker = page.locator('[data-detection-inline-frame-picker]');
        await expect(picker).toHaveCount(1);
        await settle(page);
        const loading = await picker.boundingBox();
        list.release();
        await expect(page.locator('[data-frame-strip] button[aria-pressed]')).toHaveCount(2);
        await settle(page);
        const loaded = await picker.boundingBox();
        expect(Math.abs((loaded?.height ?? 0) - (loading?.height ?? 0)), 'the strip grew when its frames arrived').toBeLessThanOrEqual(1);
    });

    test('switching capture while the old one is still loading shows only the new capture', async ({ page }) => {
        const plan = newPlan();
        const titList = gate();
        const titPhoto = gate();
        plan.heldLists.set('tit', titList.promise);
        plan.held.set('/api/frigate/tit/', titPhoto.promise);
        plan.missing.push('/api/frigate/tit/');
        await openRecord(page, plan);
        await page.evaluate(() => window.reviewMedia?.setRecord('robin'));
        await expect.poll(async () => (await images(page, '[data-detection-photograph]')).some((image) => image.loaded && image.src.includes('/robin/'))).toBe(true);
        titList.release();
        titPhoto.release();
        await page.waitForTimeout(250);
        const shown = await images(page, '[data-detection-photograph]');
        expect(shown.every((image) => image.src.includes('/robin/')), JSON.stringify(shown)).toBe(true);
        expect(shown.filter((image) => image.broken)).toEqual([]);
        expect(plan.errors).toEqual([]);
    });
});

test.describe('Needs your call after a reclassification settles', () => {
    test('the open capture rereads its photograph and frames when its run settles, and on nothing else', async ({ page }) => {
        const plan = newPlan();
        await openQueue(page, plan);
        const listReads = () => plan.requests.filter((request) => /^GET \/api\/frigate\/tit\/snapshot\/candidates$/.test(request)).length;
        await expect.poll(listReads).toBe(1);
        await expect.poll(async () => (await queuePhoto(page)).images.some((image) => image.loaded)).toBe(true);
        const before = (await queuePhoto(page)).images[0]?.src;
        expect(before).toContain('/api/frigate/tit/snapshot.jpg');

        await page.evaluate(() => {
            window.reviewMedia?.progressAnalysis('tit', 12);
            window.reviewMedia?.completeAnalysis('robin');
        });
        await settle(page);
        expect(listReads()).toBe(1);
        expect((await queuePhoto(page)).images[0]?.src).toBe(before);

        const list = gate();
        plan.heldLists.set('tit', list.promise);
        await page.evaluate(() => window.reviewMedia?.completeAnalysis('tit'));
        await expect.poll(listReads).toBe(2);
        // The same capture is reread in place: its frames stay while the new list is on its way.
        await expect(page.locator('[data-frame-strip-pending]')).toHaveCount(0);
        list.release();
        await expect.poll(async () => (await queuePhoto(page)).images.find((image) => image.loaded)?.src).not.toBe(before);
        expect((await queuePhoto(page)).images.find((image) => image.loaded)?.src).toContain('/api/frigate/tit/snapshot.jpg');
        expect(plan.errors).toEqual([]);
    });
});

// Twenty-two choices: twenty earlier photographs, then the wren's two frames, the later of which
// is the photograph. Far more than any record or queue width shows at once, so the strip has a
// start, a middle and an end, and the photograph in use sits at the far end.
const MANY_KEPT = Array.from({ length: 20 }, (_, index) => `kept${String(index).padStart(2, '0')}cafe`);
const FIRST_KEPT = `retained_snapshot__${MANY_KEPT[0]}`;

interface StripView { scrollLeft: number; maxScroll: number; reachable: number[]; chosen: number; chosenReachable: boolean }

/**
 * Which thumbnails a pointer can actually land on right now: inside the strip's visible width
 * and not under an edge control or anything else. A thumbnail half off the edge is not reached.
 */
async function stripView(page: Page): Promise<StripView> {
    return page.locator('[data-frame-strip-scroller]').evaluate((scroller) => {
        const view = scroller.getBoundingClientRect();
        const triggers = [...scroller.querySelectorAll<HTMLElement>('button[aria-pressed]')];
        const reachableAt = (trigger: HTMLElement) => {
            const rect = trigger.getBoundingClientRect();
            if (rect.left < view.left - 1 || rect.right > view.right + 1) return false;
            // Both ends of the thumbnail, so a control covering half of it does not count.
            return [rect.left + 6, rect.right - 6].every((x) => {
                const hit = document.elementFromPoint(x, rect.top + rect.height / 2);
                return hit !== null && trigger.contains(hit);
            });
        };
        const reachable = triggers.flatMap((trigger, index) => (reachableAt(trigger) ? [index] : []));
        const chosen = triggers.findIndex((trigger) => trigger.getAttribute('aria-pressed') === 'true');
        return {
            scrollLeft: Math.round(scroller.scrollLeft),
            maxScroll: scroller.scrollWidth - scroller.clientWidth,
            reachable,
            chosen,
            chosenReachable: chosen >= 0 && reachable.includes(chosen)
        };
    });
}

/**
 * Where a thumbnail sits, by geometry alone: wholly inside the strip's visible width and clear of
 * any edge control that is showing. Unlike stripView this holds while a phone's comparison sheet
 * covers the strip, so keyboard focus can be checked before the sheet is dismissed.
 */
async function thumbnailPlacement(page: Page, index: number): Promise<{ inStrip: boolean; clearOfControls: boolean }> {
    return page.locator('[data-frame-strip-scroller]').evaluate((scroller, at) => {
        const view = scroller.getBoundingClientRect();
        const trigger = scroller.querySelectorAll<HTMLElement>('button[aria-pressed]')[at];
        const rect = trigger.getBoundingClientRect();
        const controls = [...document.querySelectorAll<HTMLElement>('[data-frame-strip-back], [data-frame-strip-forward]')]
            .filter((control) => getComputedStyle(control).visibility !== 'hidden')
            .map((control) => control.getBoundingClientRect());
        return {
            inStrip: rect.left >= view.left - 1 && rect.right <= view.right + 1,
            clearOfControls: controls.every((control) => rect.right <= control.left + 1 || rect.left >= control.right - 1)
        };
    }, index);
}

async function settledStrip(page: Page): Promise<StripView> {
    let previous = -1;
    // Let immediate focus/layout updates settle. Edge navigation also waits for scrollend below;
    // unchanged samples alone do not establish that a native smooth scroll has finished.
    await expect.poll(async () => {
        const now = (await stripView(page)).scrollLeft;
        const still = now === previous;
        previous = now;
        return still;
    }, { intervals: [80] }).toBe(true);
    return stripView(page);
}

async function scrollStripWithEdge(page: Page, direction: 'forward' | 'back'): Promise<StripView> {
    const scroller = page.locator('[data-frame-strip-scroller]');
    // Two unchanged polling samples can occur while a busy renderer has not started its next
    // scroll frame. Install the listener before the click, including for reduced-motion scrolling.
    await scroller.evaluate(element => {
        element.setAttribute('data-test-scroll-finished', 'false');
        element.addEventListener('scrollend', () => {
            element.setAttribute('data-test-scroll-finished', 'true');
        }, { once: true });
    });
    await page.locator(`[data-frame-strip-${direction}]`).click();
    await expect(scroller).toHaveAttribute('data-test-scroll-finished', 'true');
    return settledStrip(page);
}

test.describe('a strip with more choices than fit', () => {
    test('edge navigation waits for a delayed smooth scroll before measuring the next choices', async ({ page }) => {
        const plan = newPlan();
        plan.retainedPhotos = MANY_KEPT;
        plan.selection.wren = FIRST_KEPT;
        await openRecord(page, plan, '&queue=wren');
        const scroller = page.locator('[data-frame-strip-scroller]');
        await expect(scroller.locator('button[aria-pressed]')).toHaveCount(22);
        const before = await settledStrip(page);
        // A busy renderer can leave two polling samples unchanged before native scrolling starts.
        // Delay that boundary explicitly so the assertion does not depend on runner load.
        await scroller.evaluate(element => {
            const scroll = element.scrollBy.bind(element);
            element.scrollBy = ((options: ScrollToOptions) => {
                setTimeout(() => scroll(options), 250);
            }) as typeof element.scrollBy;
        });
        const after = await scrollStripWithEdge(page, 'forward');
        expect(after.scrollLeft).toBeGreaterThan(before.scrollLeft);
        expect(after.reachable.some(index => !before.reachable.includes(index))).toBe(true);
        expect(plan.errors).toEqual([]);
    });

    const surfaces = [
        { name: 'Needs your call', open: openQueue },
        { name: 'the detection record', open: openRecord }
    ];

    for (const surface of surfaces) {
        test(`${surface.name}: every choice is reached by the edge controls, from the start through the middle to the end`, async ({ page }, testInfo) => {
            const plan = newPlan();
            plan.retainedPhotos = MANY_KEPT;
            plan.selection.wren = FIRST_KEPT;
            await surface.open(page, plan, '&queue=wren');
            const strip = page.locator('[data-frame-strip]');
            const triggers = strip.locator('button[aria-pressed]');
            await expect(triggers).toHaveCount(22);
            await expect(strip).toContainText('22 photo options from this visit');
            const back = strip.locator('[data-frame-strip-back]');
            const forward = strip.locator('[data-frame-strip-forward]');

            let view = await settledStrip(page);
            expect(view.maxScroll, 'the fixture must overflow').toBeGreaterThan(200);
            expect(view.scrollLeft).toBe(0);
            expect(view.chosenReachable, 'the chosen frame starts in view').toBe(true);
            await expect(back).toBeHidden();
            await expect(forward).toBeVisible();
            await page.screenshot({ path: testInfo.outputPath('many-start.png') });

            const reached = new Set(view.reachable);
            let sawMiddle = false;
            for (let step = 0; step < 30 && view.scrollLeft < view.maxScroll - 1; step += 1) {
                view = await scrollStripWithEdge(page, 'forward');
                view.reachable.forEach((index) => reached.add(index));
                if (view.scrollLeft > 0 && view.scrollLeft < view.maxScroll - 1 && !sawMiddle) {
                    sawMiddle = true;
                    await expect(back).toBeVisible();
                    await expect(forward).toBeVisible();
                    await page.screenshot({ path: testInfo.outputPath('many-middle.png') });
                }
            }
            expect(sawMiddle, 'one press must not jump straight to the end').toBe(true);
            expect(view.scrollLeft).toBeGreaterThanOrEqual(view.maxScroll - 1);
            await expect(forward).toBeHidden();
            await expect(back).toBeVisible();
            expect(view.reachable).toContain(21);
            await page.screenshot({ path: testInfo.outputPath('many-end.png') });
            expect([...reached].sort((a, b) => a - b), 'a choice was never reachable').toEqual([...Array(22).keys()]);

            // A choice reached at the far end compares and applies like any other, and the strip
            // stays where the person left it.
            await triggers.nth(21).click();
            const panel = page.locator('[data-frame-strip-panel]');
            await expect(panel).toContainText('Photo option 22 of 22');
            if ((page.viewportSize()?.width ?? 1280) < 640) {
                // The sheet's backdrop lies over the whole modal, so a tap above the sheet closes it
                // rather than reaching the record or the queue's decisions beneath.
                const topmost = await page.evaluate(() => {
                    const hit = document.elementFromPoint(window.innerWidth / 2, 24);
                    return hit?.hasAttribute('data-frame-strip-backdrop') ?? false;
                });
                expect(topmost, 'the sheet backdrop is beneath the modal').toBe(true);
            }
            await panel.getByRole('button', { name: 'Use this photo' }).click();
            await expect.poll(() => plan.selection.wren).toBe('f40-model');
            await expect(triggers.nth(21)).toHaveAttribute('aria-pressed', 'true');
            // Its Use button gives way to a label, and focus must not fall to the page with it.
            // On a phone the comparison is a sheet over the strip that stays to show the result,
            // with focus on its Close, so Escape closes it and leaves the record open. A desktop
            // pop-out closes as the button goes, and focus returns to its thumbnail.
            if ((page.viewportSize()?.width ?? 1280) < 640) {
                await expect(panel).toContainText('The photograph now');
                await expect(panel.getByRole('button', { name: 'Close' })).toBeFocused();
                await page.keyboard.press('Escape');
            } else if (await panel.count()) {
                await page.keyboard.press('Escape');
            }
            await expect(panel).toHaveCount(0);
            await expect(page.locator('[data-frame-strip-backdrop]')).toHaveCount(0);
            await expect(page.getByRole('dialog').first()).toBeVisible();
            await expect(triggers.nth(21)).toBeFocused();
            view = await settledStrip(page);
            expect(view.chosenReachable).toBe(true);
            expect(view.scrollLeft).toBeGreaterThanOrEqual(view.maxScroll - 1);

            for (let step = 0; step < 30 && view.scrollLeft > 0; step += 1) {
                view = await scrollStripWithEdge(page, 'back');
            }
            expect(view.scrollLeft).toBe(0);
            await expect(back).toBeHidden();
            expect(plan.errors).toEqual([]);
        });

        test(`${surface.name}: a chosen photograph far along the strip is brought into view when it opens`, async ({ page }, testInfo) => {
            const plan = newPlan();
            plan.retainedPhotos = MANY_KEPT;
            await surface.open(page, plan, '&queue=wren');
            await expect(page.locator('[data-frame-strip] button[aria-pressed="true"]')).toHaveCount(1);
            const view = await settledStrip(page);
            await page.screenshot({ path: testInfo.outputPath('many-chosen-offscreen.png') });
            expect(view.chosen).toBe(21);
            expect(view.scrollLeft).toBeGreaterThan(0);
            expect(view.chosenReachable, JSON.stringify(view)).toBe(true);
            await expect(page.locator('[data-frame-strip-back]')).toBeVisible();
        });
    }

    test('the keyboard moves along the strip and every thumbnail it reaches is in view', async ({ page }) => {
        const plan = newPlan();
        plan.retainedPhotos = MANY_KEPT;
        await openQueue(page, plan, '&queue=wren');
        const triggers = page.locator('[data-frame-strip] button[aria-pressed]');
        await expect(triggers).toHaveCount(22);
        const panel = page.locator('[data-frame-strip-panel]');
        const sheet = (page.viewportSize()?.width ?? 1280) < 640;

        // Keyboard focus opens the comparison for its thumbnail: a pop-out beside it, or on a
        // phone a sheet over the strip. Either way the thumbnail is placed clear of the edges,
        // Escape closes the comparison and leaves focus where it was, and the thumbnail is then
        // one a finger or pointer actually lands on.
        const checkFocused = async (index: number, why: string) => {
            await expect(triggers.nth(index)).toBeFocused();
            await settledStrip(page);
            // An edge control fades for 150 ms after its end comes into view.
            await expect.poll(() => thumbnailPlacement(page, index), { message: why }).toEqual({ inStrip: true, clearOfControls: true });
            await expect(panel).toContainText(`Photo option ${index + 1} of 22`);
            await expect(page.locator('[data-frame-strip-backdrop]')).toHaveCount(sheet ? 1 : 0);
            await page.keyboard.press('Escape');
            await expect(panel).toHaveCount(0);
            await expect(page.locator('[data-frame-strip-backdrop]')).toHaveCount(0);
            await expect(triggers.nth(index)).toBeFocused();
            expect((await settledStrip(page)).reachable, why).toContain(index);
        };

        // The photograph in use is the last of them, so the strip opens at its far end.
        await triggers.nth(0).focus();
        await checkFocused(0, 'Tab-style focus landed under the edge');

        for (let index = 1; index <= 12; index += 1) {
            await page.keyboard.press('ArrowRight');
            await expect(triggers.nth(index)).toBeFocused();
            // The comparison follows focus along the strip.
            await expect(panel).toContainText(`Photo option ${index + 1} of 22`);
        }
        await checkFocused(12, 'focus moved onto a thumbnail hidden under the edge');

        await page.keyboard.press('End');
        await checkFocused(21, 'End left the last thumbnail under the edge');

        await page.keyboard.press('ArrowLeft');
        await expect(triggers.nth(20)).toBeFocused();

        await page.keyboard.press('Home');
        await checkFocused(0, 'Home left the first thumbnail under the edge');

        // Down still carries focus into the comparison, as it did before the strip could scroll.
        await page.keyboard.press('ArrowDown');
        await expect(panel).toContainText('Photo option 1 of 22');
        await expect(panel.getByRole('button', { name: 'Close' })).toBeFocused();
        expect(plan.errors).toEqual([]);
    });

    test('on a narrow phone the strip stays inside the screen and its ends are reached by tap and by swipe', async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 360, height: 780 });
        const plan = newPlan();
        plan.retainedPhotos = MANY_KEPT;
        plan.selection.wren = FIRST_KEPT;
        await openQueue(page, plan, '&queue=wren');
        const strip = page.locator('[data-frame-strip]');
        await expect(strip.locator('button[aria-pressed]')).toHaveCount(22);
        let view = await settledStrip(page);
        expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360);
        const box = await page.locator('[data-frame-strip-scroller]').boundingBox();
        expect((box?.x ?? -1) >= 0 && (box?.x ?? 0) + (box?.width ?? 0) <= 360).toBe(true);
        expect(view.reachable.length).toBeGreaterThanOrEqual(3);

        const forward = strip.locator('[data-frame-strip-forward]');
        const back = strip.locator('[data-frame-strip-back]');
        const target = await forward.boundingBox();
        expect(target?.width ?? 0, 'the edge control is too small to tap').toBeGreaterThanOrEqual(24);
        expect(target?.height ?? 0, 'the edge control is too small to tap').toBeGreaterThanOrEqual(24);
        view = await scrollStripWithEdge(page, 'forward');
        expect(view.scrollLeft).toBeGreaterThan(0);
        await page.screenshot({ path: testInfo.outputPath('many-phone-middle.png') });

        // A swipe is the strip's own scrolling; the controls follow it.
        await page.locator('[data-frame-strip-scroller]').evaluate((scroller) => { scroller.scrollLeft = scroller.scrollWidth; });
        view = await settledStrip(page);
        await expect(forward).toBeHidden();
        await expect(back).toBeVisible();
        expect(view.reachable).toContain(21);
        await page.screenshot({ path: testInfo.outputPath('many-phone-end.png') });
        expect(plan.errors).toEqual([]);
    });
});

interface Fit {
    viewport: { width: number; height: number };
    overlay: { x: number; y: number; width: number; height: number };
    dialog: { x: number; y: number; width: number; height: number };
    openerTop: number;
    scrollY: number;
}

async function fit(page: Page): Promise<Fit> {
    return page.evaluate(() => {
        const rect = (element: Element | null) => {
            const box = element?.getBoundingClientRect();
            return { x: box?.x ?? NaN, y: box?.y ?? NaN, width: box?.width ?? NaN, height: box?.height ?? NaN };
        };
        return {
            // The visual viewport is what a person sees, scrollbars included.
            viewport: { width: window.innerWidth, height: window.innerHeight },
            overlay: rect(document.querySelector('[data-review-queue-modal]')),
            dialog: rect(document.querySelector('[data-review-queue-modal] [role="dialog"]')),
            openerTop: rect(document.querySelector('[data-open-queue]')).y,
            scrollY: window.scrollY
        };
    });
}

test.describe('Needs your call over a long, scrolled page', () => {
    for (const text of ['100%', '200%'] as const) {
        test(`${text} text: the queue covers the screen, holds the page still and hands it back where it was`, async ({ page, isMobile }, testInfo) => {
            const plan = newPlan();
            await serve(page, plan);
            await page.goto('/browser-tests/review-media.html?surface=queue&page=tall&theme=dark', { waitUntil: 'domcontentloaded' });
            if (text !== '100%') await page.addStyleTag({ content: `html{font-size:${text}!important}` });
            const opener = page.locator('[data-open-queue]');
            await expect(opener).toBeVisible();
            // Quark's dashboard was 1173px down when the queue opened over it.
            await page.evaluate(() => window.scrollTo(0, 1173));
            await expect(opener).toBeInViewport();
            const before = await fit(page);
            expect(before.scrollY).toBeGreaterThan(1000);
            // From the keyboard, so every engine has an opener to hand focus back to (WebKit does
            // not focus a clicked button).
            await opener.focus();
            await page.keyboard.press('Enter');
            await expect(page.locator('[data-review-species-heading]')).toBeVisible();
            await settle(page);

            const open = await fit(page);
            await page.screenshot({ path: testInfo.outputPath(`scrolled-page-${text.replace('%', '')}.png`) });
            const { width, height } = open.viewport;
            // The backdrop reaches every edge: no strip of page or page scrollbar beside or below it.
            expect(open.overlay).toEqual({ x: 0, y: 0, width, height });
            // The dialog sits wholly on screen, and on a phone it is the screen.
            expect(open.dialog.x).toBeGreaterThanOrEqual(0);
            expect(open.dialog.y).toBeGreaterThanOrEqual(0);
            expect(open.dialog.x + open.dialog.width).toBeLessThanOrEqual(width);
            expect(open.dialog.y + open.dialog.height).toBeLessThanOrEqual(height);
            if (width < 640) expect(open.dialog).toEqual({ x: 0, y: 0, width, height });

            // The page behind does not move while the queue is open, by script or by wheel.
            await page.evaluate(() => window.scrollBy(0, 400));
            if (!isMobile) {
                const photo = await page.locator('[data-review-photograph]').boundingBox();
                await page.mouse.move((photo?.x ?? 0) + 20, (photo?.y ?? 0) + 20);
                await page.mouse.wheel(0, 600);
            }
            await settle(page);
            expect((await fit(page)).openerTop).toBe(before.openerTop);

            // The last decision is reached inside the dialog and stays on screen.
            const last = page.getByRole('button', { name: 'Not a bird, hide it', exact: true });
            await last.scrollIntoViewIfNeeded();
            const lastBox = await last.boundingBox();
            expect(lastBox?.y ?? -1).toBeGreaterThanOrEqual(0);
            expect((lastBox?.y ?? 0) + (lastBox?.height ?? height + 1)).toBeLessThanOrEqual(height);
            expect((await fit(page)).openerTop).toBe(before.openerTop);
            // Text wraps rather than pushing anything sideways: only the frame strip scrolls across.
            const sideways = await page.locator('[data-review-queue-modal] [role="dialog"]').evaluate((dialog) =>
                [dialog, ...dialog.querySelectorAll('*')].filter((element) =>
                    ['auto', 'scroll'].includes(getComputedStyle(element).overflowX)
                    && element.scrollWidth > element.clientWidth + 1
                    && !element.matches('[data-frame-strip-scroller]')).length);
            expect(sideways, 'something in the dialog scrolls sideways').toBe(0);
            // The dialog's name is read whole, not cut short, at any text size.
            const title = page.locator('#review-session-title');
            expect(await title.evaluate((element) => element.scrollWidth <= element.clientWidth)).toBe(true);
            await expect(title).toHaveText('Needs your call');
            // Nor are the species names a choice is made from.
            const names = page.locator('[aria-labelledby="review-species-choices"] button > span:first-child > span');
            expect(await names.count()).toBeGreaterThan(0);
            expect(await names.evaluateAll((spans) => spans.filter((span) => span.scrollWidth > span.clientWidth).length)).toBe(0);

            await page.keyboard.press('Escape');
            await expect(page.locator('[data-review-queue-modal]')).toHaveCount(0);
            await expect(opener).toBeFocused();
            const after = await fit(page);
            expect(after.scrollY).toBe(before.scrollY);
            expect(after.openerTop).toBe(before.openerTop);
            // And the page scrolls again once it is handed back.
            await page.evaluate(() => window.scrollBy(0, 200));
            expect((await fit(page)).scrollY).toBe(before.scrollY + 200);
            expect(plan.errors).toEqual([]);
        });
    }

    test('handing over to the full record keeps the page still, and closing the record returns it', async ({ page }) => {
        const plan = newPlan();
        await serve(page, plan);
        await page.goto('/browser-tests/review-media.html?surface=queue&page=tall', { waitUntil: 'domcontentloaded' });
        const opener = page.locator('[data-open-queue]');
        await expect(opener).toBeVisible();
        await page.evaluate(() => window.scrollTo(0, 1173));
        const before = await fit(page);
        await opener.click();
        await page.getByRole('button', { name: 'Open full record', exact: true }).click();
        const record = page.locator('[data-detection-detail-modal]');
        await expect(record).toBeVisible();
        await expect(page.locator('[data-review-queue-modal]')).toHaveCount(0);
        await settle(page);
        await page.evaluate(() => window.scrollBy(0, 400));
        expect((await fit(page)).openerTop).toBe(before.openerTop);

        await record.getByRole('button', { name: 'Close', exact: true }).first().click();
        await expect(record).toHaveCount(0);
        const after = await fit(page);
        expect(after.scrollY).toBe(before.scrollY);
        expect(after.openerTop).toBe(before.openerTop);
        await page.evaluate(() => window.scrollBy(0, 200));
        expect((await fit(page)).scrollY).toBe(before.scrollY + 200);
        expect(plan.errors).toEqual([]);
    });
});
