import { expect, test, type Locator, type Page } from '@playwright/test';
import recording from './fixtures/accessibility-api.json' with { type: 'json' };
import { replayFeeder, settled } from './accessibility-mock';

/**
 * One record, the same controls wherever it opens. The record is opened from About, the Dashboard
 * and the Explorer; only access (owner, or a guest under the owner's switches) changes what it offers.
 */
const READY = { timeout: 15_000 };
// A cold dev server compiles each route on its first request, so a first paint can take far longer
// than a warm one. The tests wait for what they need to be drawn, never for a fixed time.
const FIRST_PAINT = { timeout: 60_000 };
test.describe.configure({ timeout: 120_000 });
// The newest recorded visit, which has a clip.
const EVENT = '1794671895.363257-to87lz';

type Responses = Record<string, { json?: unknown }>;
const RESPONSES = (recording as { responses: Responses }).responses;
const RECORD = (RESPONSES['/api/events?limit=50&offset=0'].json as { frigate_event: string }[]).find((row) => row.frigate_event === EVENT);
const VISITS = RESPONSES['/api/visits?limit=24&offset=0&sort=newest'].json as { visits: unknown[] };
const VISIT = VISITS.visits.find((visit) => JSON.stringify(visit).includes(EVENT));

interface Viewer { guest: boolean; showClips?: boolean }

async function openFeeder(page: Page, viewer: Viewer): Promise<void> {
    if (!RECORD || !VISIT) throw new Error('The recording no longer holds the record this test opens');
    await replayFeeder(page, 'light', {}, (json, url) => {
        if (url.pathname === '/api/auth/status' && viewer.guest) {
            return {
                ...(json as Record<string, unknown>),
                auth_required: true,
                is_authenticated: false,
                public_access_enabled: true,
                public_access_show_clips: viewer.showClips ?? true
            };
        }
        if (url.pathname === '/api/about/portrait') {
            const record = RECORD as unknown as { detection_time: string; display_name: string; scientific_name?: string };
            return {
                ...(json as Record<string, unknown>),
                latest_visit: {
                    frigate_event: EVENT,
                    detection_time: record.detection_time,
                    display_name: record.display_name,
                    scientific_name: record.scientific_name ?? null,
                    image_url: `/api/frigate/${EVENT}/snapshot.jpg`,
                    film_url: null
                }
            };
        }
        // A read for one event answers with that event, as the server does.
        if (url.pathname === '/api/events' && url.searchParams.get('event_id') === EVENT) return [RECORD];
        // The Dashboard's log leads with the same visit the other pages open.
        if (url.pathname === '/api/visits') return { ...(json as Record<string, unknown>), visits: [VISIT], total: 1 };
        return json;
    });
    if (viewer.guest) {
        await page.route((url) => url.pathname === '/api/settings', (route) => route.fulfill({ status: 401, json: { detail: 'Not authenticated' } }));
    }
    // The clip never finishes arriving, which leaves the player open on its controls.
    await page.route((url) => /\/api\/frigate\/[^/]+\/(?:recording-)?clip\.mp4$/.test(url.pathname), async (route) => {
        if (route.request().method() === 'HEAD') return route.fulfill({ status: 200 });
        await new Promise(() => {});
    });
}

function record(page: Page): Locator {
    return page.locator('[data-detection-detail-modal]');
}

/** The record is a lazy chunk; it is open once its close button and its photograph are drawn. */
async function recordOpen(page: Page): Promise<void> {
    await expect(record(page).locator('[data-detection-modal-close]')).toBeVisible(FIRST_PAINT);
    await expect(record(page).locator('[data-detection-photograph]')).toBeVisible(READY);
}

async function openFromAbout(page: Page): Promise<void> {
    await page.goto('/about');
    const visit = page.locator('[data-feeder-portrait-visit]');
    await expect(visit).toBeVisible(FIRST_PAINT);
    await visit.click();
    await recordOpen(page);
}

async function openFromDashboard(page: Page): Promise<void> {
    await page.goto('/');
    await expect(page.locator('[data-field-log-row]').first()).toBeVisible(FIRST_PAINT);
    await page.locator('[data-field-log-row] [data-field-log-action]').first().click();
    await recordOpen(page);
}

async function openFromExplorer(page: Page): Promise<void> {
    await page.goto(`/events?event=${encodeURIComponent(EVENT)}`);
    await recordOpen(page);
}

function playButton(page: Page): Locator {
    return record(page).getByRole('button', { name: /^Play (?:video|full visit clip) of / });
}

/** The names of every control the open record offers, its menu of further actions included. */
async function controls(page: Page): Promise<string[]> {
    await settled(page);
    const more = record(page).locator('[data-detection-more-actions]');
    if (await more.count()) await more.click();
    const names = await record(page).getByRole('button').evaluateAll((buttons) =>
        buttons.filter((button) => (button as HTMLElement).offsetParent !== null).map((button) => (button.getAttribute('aria-label') ?? button.textContent ?? '').replace(/\s+/g, ' ').trim())
    );
    return [...new Set(names)].sort();
}

test.describe('the record opened from About', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('offers the owner its video, which opens in the player', async ({ page }) => {
        await openFeeder(page, { guest: false });
        await openFromAbout(page);
        await expect(playButton(page)).toBeVisible();
        await playButton(page).click();
        // The player replaces the record, so one dialog is open at a time.
        await expect(page.locator('#video-player-title')).toBeVisible(READY);
        await expect(record(page)).toHaveCount(0);
        await expect(page.getByRole('dialog').getByRole('button', { name: 'Share link' })).toBeVisible(READY);
    });

    test('offers a guest the video while the owner shares clips', async ({ page }) => {
        await openFeeder(page, { guest: true, showClips: true });
        await openFromAbout(page);
        await expect(playButton(page)).toBeVisible();
        await playButton(page).click();
        await expect(page.locator('#video-player-title')).toBeVisible(READY);
        // A guest is never offered sharing, and downloads stay off while the owner has not allowed them.
        await expect(page.getByRole('dialog').getByRole('button', { name: 'Share link' })).toHaveCount(0);
        await expect(page.getByRole('dialog').getByRole('link', { name: 'Download clip' })).toHaveCount(0);
    });

    test('offers a guest no video while the owner keeps clips private', async ({ page }) => {
        await openFeeder(page, { guest: true, showClips: false });
        await openFromAbout(page);
        await settled(page);
        await expect(playButton(page)).toHaveCount(0);
        // The owner's own actions stay the owner's.
        await expect(record(page).locator('[data-detection-more-actions]')).toHaveCount(0);
    });
});

test.describe('the same record from each page', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    for (const viewer of [{ guest: false }, { guest: true, showClips: true }, { guest: true, showClips: false }] satisfies Viewer[]) {
        const who = viewer.guest ? `a guest with clips ${viewer.showClips ? 'shared' : 'private'}` : 'the owner';
        test(`offers ${who} the same controls from About, the Dashboard and the Explorer`, async ({ page }) => {
            await openFeeder(page, viewer);
            await openFromAbout(page);
            const fromAbout = await controls(page);
            await openFromDashboard(page);
            const fromDashboard = await controls(page);
            await openFromExplorer(page);
            const fromExplorer = await controls(page);
            expect(fromAbout.length).toBeGreaterThan(0);
            expect(fromDashboard).toEqual(fromAbout);
            expect(fromExplorer).toEqual(fromAbout);
            expect(fromAbout.some((name) => /^Play (?:video|full visit clip) of /.test(name))).toBe(!viewer.guest || viewer.showClips === true);
        });
    }
});

test.describe('the Explorer\'s own play buttons', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    for (const showClips of [true, false]) {
        test(`follow the guest switch with clips ${showClips ? 'shared' : 'private'}, on cards and in the list`, async ({ page }) => {
            await openFeeder(page, { guest: true, showClips });
            await page.goto('/events');
            await expect(page.locator('[data-detection-card]').first()).toBeVisible(FIRST_PAINT);
            await settled(page);
            const play = page.getByRole('button', { name: /^Play video of / });
            if (showClips) await expect(play.first()).toBeVisible();
            else await expect(play).toHaveCount(0);
            await page.getByRole('button', { name: 'List', exact: true }).click();
            await expect(page.locator('[data-detection-row]').first()).toBeVisible(READY);
            await settled(page);
            if (showClips) await expect(play.first()).toBeVisible();
            else await expect(play).toHaveCount(0);
        });
    }
});
