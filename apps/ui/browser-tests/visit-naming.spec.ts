import { test, expect, type Page } from '@playwright/test';

// Set VISIT_SHOTS to a directory to keep review screenshots outside the test output.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};
const shots = environment.VISIT_SHOTS;

/**
 * The owner's case of 2026-11-26: six Blue Tit captures are one visit. The busiest capture holds
 * a Wood Pigeon too, but the visit shows and opens a later, Blue-Tit-only capture.
 */
const PEAK = '1795697047.371675-hqfh0o';
const SHOWN = '1795697188.078259-cforck';
const minutesAgo = (minutes: number, seconds = 0) => new Date(Date.now() - minutes * 60_000 + seconds * 1000).toISOString();
const START = minutesAgo(62);
const END = minutesAgo(60, 1);

function blueTit(id: string, at: string, overrides: Record<string, unknown> = {}) {
    return {
        frigate_event: id, display_name: 'Cyanistes caeruleus', category_name: 'Cyanistes caeruleus', scientific_name: 'Cyanistes caeruleus',
        common_name: 'Eurasian Blue Tit', camera_name: 'birdcam', detection_time: at, score: 0.99, has_clip: true, ...overrides
    };
}

const peak = blueTit(PEAK, START, {
    score: 0.9,
    bird_summary: { counted: 2, unknown: 0, excluded: 0, hint_only: false, species: [
        { species: 'Columba palumbus', count: 1, common_name: 'Common Wood-Pigeon', scientific_name: 'Columba palumbus' },
        { species: 'Cyanistes caeruleus', count: 1, common_name: 'Eurasian Blue Tit', scientific_name: 'Cyanistes caeruleus' }
    ] }
});
const shown = blueTit(SHOWN, minutesAgo(60));

function candidates(event: string) {
    return {
        event_id: event, current_source: 'hq_candidate_model_crop', current_candidate_id: `${event}__a`, as_recorded_dismissed: false, birds: [],
        candidates: ['a', 'b', 'c'].map((id, index) => ({
            candidate_id: `${event}__${id}`, frame_index: index * 40, frame_offset_seconds: index * 2, source_mode: 'model_crop', clip_variant: 'event',
            crop_box: [10, 10, 90, 90], crop_confidence: 0.7, classifier_label: 'Cyanistes caeruleus', classifier_score: 0.9, ranking_score: 0.9 - index / 10,
            selected: id === 'a', photo_hidden: false, snapshot_source: 'hq_candidate_model_crop',
            image_url: `/api/frigate/${event}/snapshot/candidates/${event}__${id}/image.jpg`,
            thumbnail_url: `/api/frigate/${event}/snapshot/candidates/${event}__${id}/thumbnail.jpg`
        }))
    };
}

interface ExplorerOptions {
    theme?: 'light' | 'dark';
    fonts?: boolean;
    /** The length the server measured on the full clip; absent when it has not measured one. */
    clipSeconds?: string | null;
    /** Further address, such as a link to one capture. */
    query?: string;
}

async function openExplorer(page: Page, { theme = 'light', fonts = false, clipSeconds = '30.2', query = '' }: ExplorerOptions = {}) {
    const errors: string[] = [];
    const requests: string[] = [];
    page.on('pageerror', error => { if (!error.message.includes('ResizeObserver loop')) errors.push(error.message); });
    if (!fonts) {
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
    }
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        requests.push(`${request.method()} ${path}`);
        if (path === '/api/settings') {
            return route.fulfill({ json: {
                enrichment_summary_provider: 'disabled', clips_enabled: true, recording_clip_enabled: true,
                // Today's settings would cut a 120-second clip; the clips on file were cut at 30.
                recording_clip_before_seconds: 30, recording_clip_after_seconds: 90, display_common_names: true
            } });
        }
        if (path === '/api/events') return route.fulfill({ json: [shown] });
        if (path === '/api/explorer/search') {
            const asked = new URL(request.url()).searchParams.get('q');
            const record = asked === SHOWN
                ? { kind: 'detection', id: SHOWN, observed_at: shown.detection_time, display_name: 'Eurasian Blue Tit', scientific_name: 'Cyanistes caeruleus', common_name: 'Eurasian Blue Tit', camera: 'birdcam', hidden: false }
                : null;
            return route.fulfill({ json: { taxa: [], truncated: false, record } });
        }
        if (path === '/api/visits') {
            return route.fulfill({ json: { total: 1, gap_seconds: 60, visits: [{
                visit_id: PEAK, start_time: START, end_time: END, capture_count: 6, best_score: 0.99, needs_review: false,
                audio_confirmed: false, representative: shown, latest: shown, peak_capture: peak
            }] } });
        }
        if (path.endsWith('/recording-clip.mp4') && request.method() === 'HEAD') {
            const headers: Record<string, string> = { 'X-YAWAMF-Recording-Clip-State': 'complete' };
            if (clipSeconds !== null) headers['X-YAWAMF-Recording-Clip-Duration'] = clipSeconds;
            return route.fulfill({ status: 200, headers, body: '' });
        }
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: { available: true, high_quality_bird_crop_enabled: true, source: 'hq_candidate_model_crop', original_frigate_snapshot_available: false } });
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: candidates(decodeURIComponent(path.split('/')[3])) });
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 6, favorites: 0, audio_matched: 0 } } });
        if (path.endsWith('.jpg')) {
            const colour = path.includes(PEAK) ? '#7c2d12' : '#4d7c0f';
            return route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="160" height="120"><rect width="160" height="120" fill="${colour}"/></svg>` });
        }
        if (path.startsWith('/api/audio/context/') || path.endsWith('/labels') || path.endsWith('/species')) return route.fulfill({ json: [] });
        return route.fulfill({ json: { count: 0 } });
    });
    await page.goto(`/browser-tests/owner-history.html?surface=explorer&settings=late${theme === 'dark' ? '&theme=dark' : ''}${query}`);
    if (!query) await expect(page.locator(`[data-explorer-visit="${PEAK}"] [data-detection-card]`)).toBeVisible();
    if (fonts) {
        // The owner reads the app in Classic, which the theme store sets on <html>.
        await page.evaluate(async () => {
            document.documentElement.style.setProperty('--font-body', "'Source Serif 4', 'Georgia', serif");
            document.documentElement.style.setProperty('--font-display', "'Playfair Display', 'Source Serif 4', serif");
            await document.fonts.ready;
        });
    }
    return { errors, requests };
}

const openedRecord = (requests: string[], event: string) => requests.some(request => request.includes(`/${event}/snapshot/candidates`));

test('a Blue Tit visit keeps its name, and the pigeon in one capture is a note that opens that capture', async ({ page }) => {
    const { errors, requests } = await openExplorer(page);
    const card = page.locator(`[data-explorer-visit="${PEAK}"] [data-detection-card]`);
    await expect(card.getByRole('heading', { level: 2 })).toHaveText('Eurasian Blue Tit');
    await expect(card).not.toContainText('Multiple species');
    // One score is the visit's own again, since the name is one species.
    await expect(card.locator('[data-detection-score]')).toHaveCount(1);

    const note = card.locator(`[data-visit-companions="${PEAK}"]`);
    // A capture, not a photo: the card's thumbnail is a crop of one bird, so the pigeon is not in it.
    await expect(note).toHaveText('Also in one capture: Common Wood-Pigeon');
    await expect(note).toHaveAccessibleName(/^Also in one capture: Common Wood-Pigeon\. Open the capture at \d{2}:\d{2}:\d{2}$/);
    await note.click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await expect.poll(() => openedRecord(requests, PEAK)).toBe(true);
    expect(openedRecord(requests, SHOWN)).toBe(false);
    // The pigeon capture is one of this visit's six, so the record says so with this visit's span.
    await expect(dialog.locator('[data-detection-visit-span]')).toContainText(/6 captures, \d{2}:\d{2}–\d{2}:\d{2}/);
    expect(errors).toEqual([]);
});

test('the list row names the visit by its species, shows one photo, and its note opens the pigeon capture', async ({ page }) => {
    const { errors, requests } = await openExplorer(page);
    await page.locator('[data-explorer-view-toggle="list"]').click();
    const row = page.locator(`[data-explorer-visit="${PEAK}"] [data-detection-row]`);
    await expect(row).toContainText('Eurasian Blue Tit');
    await expect(row).not.toContainText('Multiple species');
    await expect(row.locator('[data-detection-preview-stack]')).toHaveCount(0);
    await expect(row.locator('[data-detection-score]')).toHaveCount(1);
    await row.locator(`[data-visit-companions="${PEAK}"]`).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect.poll(() => openedRecord(requests, PEAK)).toBe(true);
    expect(errors).toEqual([]);
});

test("the record says its clip and photo options are this capture's, and that it is part of a longer visit", async ({ page }) => {
    const { errors, requests } = await openExplorer(page);
    await page.getByRole('button', { name: 'Eurasian Blue Tit detected at birdcam', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect.poll(() => openedRecord(requests, SHOWN)).toBe(true);

    const visit = dialog.locator('[data-detection-visit-span]');
    await expect(visit).toContainText('Part of a visit');
    await expect(visit).toContainText(/6 captures, \d{2}:\d{2}–\d{2}:\d{2}/);

    // Frames when the strip only inspects, photo options when one can be chosen: either belongs to this capture.
    await expect(dialog.locator('[data-frame-strip-status]')).toContainText(/3 (?:frames|photo options) from this capture/);
    await expect(dialog).not.toContainText('from this visit');

    const play = dialog.getByRole('button', { name: "Play this capture's full clip, Eurasian Blue Tit", exact: true });
    await expect(play).toBeVisible();
    await expect(play).toHaveText('Full clip');
    await expect(play).toHaveAttribute('title', "This capture's full clip, 30 seconds");
    await expect(dialog).not.toContainText('Full visit');
    expect(errors).toEqual([]);
});

test('review screenshots of the visit card and the record', async ({ page }) => {
    test.skip(!shots, 'VISIT_SHOTS is not set');
    for (const [theme, width] of [['light', 1440], ['dark', 1440], ['light', 390]] as const) {
        await page.setViewportSize({ width, height: 900 });
        await openExplorer(page, { theme, fonts: true });
        const item = page.locator(`[data-explorer-visit="${PEAK}"]`);
        await page.waitForTimeout(300);
        await item.screenshot({ path: `${shots}/card-${width}-${theme}.png` });
        await item.locator('[data-detection-card] > div > button').first().click();
        const dialog = page.getByRole('dialog');
        await expect(dialog).toBeVisible();
        await page.waitForTimeout(800);
        await page.evaluate(() => document.fonts.ready);
        await page.screenshot({ path: `${shots}/record-${width}-${theme}.png` });
        const facts = dialog.locator('[data-detection-facts]');
        if (await facts.count()) {
            await facts.scrollIntoViewIfNeeded();
            await page.screenshot({ path: `${shots}/record-facts-${width}-${theme}.png` });
        }
        await page.unrouteAll({ behavior: 'ignoreErrors' });
    }
});

test('the full clip states the length measured on it, never one from settings, and none before it is measured', async ({ page }) => {
    const { errors } = await openExplorer(page, { clipSeconds: null });
    await page.getByRole('button', { name: 'Eurasian Blue Tit detected at birdcam', exact: true }).click();
    const play = page.getByRole('dialog').getByRole('button', { name: "Play this capture's full clip, Eurasian Blue Tit", exact: true });
    await expect(play).toBeVisible();
    await expect(play).toHaveAttribute('title', "This capture's full clip");
    expect(errors).toEqual([]);
});

test('a record opened by its link says nothing of a visit it was not opened from', async ({ page }) => {
    const { errors, requests } = await openExplorer(page, { query: `&event=${SHOWN}` });
    const dialog = page.getByRole('dialog');
    await expect.poll(() => openedRecord(requests, SHOWN)).toBe(true);
    await expect(dialog.locator('[data-detection-facts]')).toBeVisible();
    await expect(dialog.locator('[data-detection-visit-span]')).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('a closed record takes its visit with it: the same capture found by search states no visit', async ({ page }) => {
    const { errors } = await openExplorer(page);
    await page.getByRole('button', { name: 'Eurasian Blue Tit detected at birdcam', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.locator('[data-detection-visit-span]')).toContainText('6 captures');
    await dialog.locator('[data-detection-modal-close]').click();
    await expect(dialog).toHaveCount(0);

    // Search opens one capture, not a visit: whatever the Explorer read before, it states none.
    const search = page.getByRole('combobox', { name: 'Search the Explorer' });
    await search.fill(SHOWN);
    await expect(page.getByRole('option', { name: /Eurasian Blue Tit/ })).toContainText('Open record');
    await search.press('Enter');
    await expect(dialog.locator('[data-detection-facts]')).toBeVisible();
    await expect(dialog.locator('[data-detection-visit-span]')).toHaveCount(0);
    expect(errors).toEqual([]);
});
