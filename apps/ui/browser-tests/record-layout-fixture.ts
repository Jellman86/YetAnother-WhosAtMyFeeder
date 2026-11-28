import { expect, type Page } from '@playwright/test';

/** What the record layout fixture can open: a long record with every section, or a short one. */
export interface RecordOptions {
    record?: 'long' | 'short';
    theme?: 'light' | 'dark';
    guest?: boolean;
    /** The stored photograph's shape: a tall crop, or a camera's wide scene. */
    photo?: 'portrait' | 'landscape';
    /** The visit kept frames: six moments, each a crop and its whole scene, the fourth crop chosen, and a finished scan. */
    frames?: boolean;
    /** Draws the record in the Classic font theme with the real web fonts, for a screenshot; tests leave the fonts out. */
    classicFonts?: boolean;
    /** False answers the lineage route as the catalogue does for a species it does not hold; 'fails' answers with a server error. */
    lineage?: boolean | 'fails';
    /** Holds the lineage answer back until it resolves. */
    lineageHeld?: Promise<void>;
    /** With `frames`, the crops sit against the top edge of a scene that fills its frame. */
    cropAtTop?: boolean;
    /** With `frames` and `cropAtTop`, the crops run the whole height of the scene. */
    cropFullHeight?: boolean;
    /** False leaves the pictures still arriving, for a test that holds them back. */
    awaitPictures?: boolean;
    /**
     * The long record's snapshot and video readings named different birds (#804): `renamed` took
     * the video's name, `kept` kept the snapshot's, `decided` is `renamed` after the owner named it.
     */
    readings?: 'renamed' | 'kept' | 'decided';
}

const picture = (width: number, height: number): string =>
    `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">`
    + `<rect width="${width}" height="${height}" fill="#6ea83a"/>`
    + `<path d="M0 ${height * 0.82} L${width} ${height * 0.7} V${height} H0z" fill="#8a8072"/>`
    + `<ellipse cx="${width * 0.5}" cy="${height * 0.5}" rx="${Math.min(width, height) * 0.09}" ry="${Math.min(width, height) * 0.05}" fill="#111827"/>`
    + `<ellipse cx="${width * 0.5}" cy="${height * 0.52}" rx="${Math.min(width, height) * 0.04}" ry="${Math.min(width, height) * 0.03}" fill="#f8fafc"/></svg>`;

const taxon = (taxon_id: number, rank: string, scientific_name: string, name: string | null, parent_id: number | null, species_count: number, seen_species: number) => ({
    taxon_id, rank, scientific_name, name, source: 'ioc-world-bird-list', principal: true, parent_id, species_count, seen_species, seen_count: seen_species * 12
});

const LINEAGE = [
    taxon(1, 'kingdom', 'Animalia', null, null, 11276, 14),
    taxon(2, 'phylum', 'Chordata', null, 1, 11276, 14),
    taxon(10, 'class', 'Aves', 'Bird', 2, 11276, 14),
    taxon(20, 'order', 'Passeriformes', null, 10, 6700, 11),
    taxon(30, 'family', 'Corvidae', 'Crows, Jays', 20, 143, 3),
    taxon(40, 'genus', 'Pica', null, 30, 7, 1),
    taxon(50, 'species', 'Pica pica', 'Eurasian Magpie', 40, 1, 1)
];

const SIGHTINGS = ['Straws Bridge LNR', '42 Woodland Avenue, Breaston, England', 'Carr Vale DWT NR', 'Tissington (Village)', 'House, Padley Wood Lane, Pilsley'].map((location_name, index) => ({
    location_name, observed_at: `2026-11-${19 - Math.floor(index / 2)}T1${4 - index}:43:00Z`, how_many: 4 - (index % 4), obs_valid: true,
    lat: 53.2 + index * 0.02, lng: -1.4 + index * 0.03
}));

const SCENE = { width: 1280, height: 720 };
const MOMENTS = [10, 30, 50, 70, 90, 110];
const CHOSEN = 'record-layout-long__f70-crop';

/** Six moments of one visit, each kept as the bird's crop and as the whole scene it was cut from. */
function candidateList(atTop: boolean, fullHeight: boolean): Record<string, unknown> {
    const candidates = MOMENTS.flatMap((frame, index) => ['crop', 'full'].map((kind) => {
        const id = `record-layout-long__f${frame}-${kind}`;
        return {
            candidate_id: id, frame_index: frame, frame_offset_seconds: frame / 25,
            source_mode: kind === 'crop' ? 'model_crop' : 'full_frame', clip_variant: 'event',
            crop_box: kind === 'crop' ? [556 + index * 4, atTop ? 0 : 276, 724 + index * 4, fullHeight ? SCENE.width * 3 / 4 : atTop ? 168 : 444] : null,
            crop_confidence: kind === 'crop' ? 0.7 : null, classifier_label: 'Pica pica', classifier_score: kind === 'crop' ? 0.9 : 0.2,
            ranking_score: kind === 'crop' ? 0.9 : 0.2, selected: id === CHOSEN, photo_hidden: false,
            snapshot_source: `hq_candidate_${kind === 'crop' ? 'model_crop' : 'full_frame'}`,
            image_url: `/api/frigate/record-layout-long/snapshot/candidates/${id}/image.jpg?v=1`,
            thumbnail_url: `/api/frigate/record-layout-long/snapshot/candidates/${id}/thumbnail.jpg?v=1`
        };
    }));
    return { event_id: 'record-layout-long', current_source: 'hq_candidate_model_crop', current_candidate_id: CHOSEN, candidates, birds: [] };
}

/** Opens the record layout fixture with every request answered from here; nothing leaves the machine. */
export async function openRecordLayout(page: Page, size: { width: number; height: number }, options: RecordOptions = {}): Promise<void> {
    const photo = options.photo === 'landscape' ? picture(1280, 720) : picture(600, 640);
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: options.theme ?? 'light' });
    await page.route(/^https?:\/\/(?!127\.0\.0\.1)/, (route) => {
        const type = route.request().resourceType();
        if (options.classicFonts && /^https:\/\/fonts\.(?:googleapis|gstatic)\.com\//.test(route.request().url())) return route.continue();
        if (type === 'stylesheet') return route.fulfill({ contentType: 'text/css', body: '' });
        if (type === 'image') return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256"><rect width="256" height="256" fill="#d9e2d0"/></svg>' });
        return route.abort();
    });
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: options.frames ? candidateList(options.cropAtTop ?? false, options.cropFullHeight ?? false) : { candidates: [], birds: [], current_source: 'frigate_snapshot' } });
        if (path.endsWith('/birds/scan')) return route.fulfill({ json: {
            event_id: 'record-layout-long', candidate_id: url.searchParams.get('candidate_id'), status: 'completed', available: true, unavailable_reason: null,
            error: null, result_count: 1, count_status: 'complete', unconfirmed_regions: [], excluded_regions: [], retained_previous: false, updated_at: null
        } });
        if (path.includes('-full/')) return route.fulfill({ contentType: 'image/svg+xml', body: options.cropAtTop ? picture(SCENE.width, SCENE.width * 3 / 4) : picture(SCENE.width, SCENE.height) });
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'frigate_snapshot' } });
        if (route.request().resourceType() === 'image' || /\.(?:jpg|jpeg|png|webp)$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: photo });
        if (path === '/api/taxonomy/lineage') {
            await options.lineageHeld;
            if (options.lineage === 'fails') return route.fulfill({ status: 500, json: { detail: 'unavailable' } });
            return route.fulfill({ json: { lineage: options.lineage === false ? [] : LINEAGE } });
        }
        if (path === '/api/taxonomy/facts') return route.fulfill({ json: { scope: 'all', shared_days: null, facts: [] } });
        if (path === '/api/ebird/nearby') return route.fulfill({ json: { status: 'ok', results: SIGHTINGS } });
        if (/^\/api\/species\/[^/]+\/info$/.test(path)) return route.fulfill({ json: {
            title: 'Eurasian magpie', source: 'Wikipedia', summary_source: 'Wikipedia',
            extract: 'The Eurasian magpie or common magpie is a resident breeding bird throughout the northern part of the Eurasian continent. It is one of several birds in the crow family designated magpies, and belongs to the Holarctic radiation of monochrome magpies.',
            wikipedia_url: 'https://en.wikipedia.org/wiki/Eurasian_magpie', thumbnail_url: 'https://upload.wikimedia.org/magpie.jpg'
        } });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation')) return route.fulfill({ json: [] });
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.setViewportSize(size);
    const query = new URLSearchParams({ record: options.record ?? 'long', theme: options.theme ?? 'light', guest: String(options.guest ?? false), font: options.classicFonts ? 'classic' : 'default', readings: options.readings ?? '' });
    await page.goto(`/browser-tests/record-layout.html?${query.toString()}`);
    const modal = page.locator('[data-detection-detail-modal]');
    // A cold dev server re-optimises a dependency the first time a page asks for it (the map here),
    // and leaves the page that asked without its modules. Loading it again is what a browser does.
    const drawn = await modal.waitFor({ state: 'visible', timeout: 8_000 }).then(() => true, () => false);
    if (!drawn) await page.reload();
    await expect(modal).toBeVisible({ timeout: 15_000 });
    if ((options.record ?? 'long') === 'long') {
        await expect(page.locator('[data-detection-reference-sightings] li').first()).toBeVisible({ timeout: 15_000 });
        if (options.lineage === undefined || options.lineage === true) await expect(page.locator('[data-taxonomy-lineage]')).toBeVisible({ timeout: 15_000 });
    }
    if (options.awaitPictures === false) return;
    await page.evaluate(() => document.fonts.ready);
    await page.evaluate(() => Promise.all([...document.images].filter((image) => !image.complete).map((image) => new Promise((done) => {
        image.addEventListener('load', done, { once: true });
        image.addEventListener('error', done, { once: true });
        setTimeout(done, 3000);
    }))));
}
