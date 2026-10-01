import { test, expect, type Page, type Route } from '@playwright/test';

function candidateResponse(eventId: string, stale: boolean) {
    const scene = `${eventId}__full_frame__f150__fixture`;
    return {
        event_id: eventId, current_source: 'hq_candidate_full_frame', current_candidate_id: scene,
        candidates: [{ candidate_id: scene, source_mode: 'full_frame', clip_variant: 'event', frame_index: 150,
            ranking_score: 0.9, selected: true, snapshot_source: 'hq_candidate_full_frame', image_url: '/api/race-scene.svg' }],
        birds: Array.from({ length: stale ? 1 : 2 }, (_, index) => ({
            id: index + 1, bird_index: index, candidate_id: `${scene}__observed__${index}`, clip_variant: 'event', frame_index: 150,
            crop_box: [100 + index * 300, 100, 250 + index * 300, 250], detector_confidence: 0.8,
            species: stale ? 'Stale first A bird' : 'Current capture bird', classifier_label: 'Fixture bird', classifier_score: 0.9,
            manual_species: false, is_hidden: false, is_unknown: false
        }))
    };
}

interface CandidateFixture { held: Route | null; heldRefresh: Route | null; holdRefresh: boolean; requestsA: number; errors: string[]; }

async function open(page: Page): Promise<CandidateFixture> {
    const fixture: CandidateFixture = { held: null, heldRefresh: null, holdRefresh: false, requestsA: 0, errors: [] };
    page.on('pageerror', error => fixture.errors.push(error.message));
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        const match = /^\/api\/frigate\/(A|B)\/snapshot\/candidates$/.exec(path);
        if (match) {
            if (match[1] === 'A') {
                fixture.requestsA += 1;
                if (fixture.requestsA === 1) { fixture.held = route; return; }
                if (fixture.holdRefresh) { fixture.heldRefresh = route; return; }
            }
            return route.fulfill({ json: candidateResponse(match[1], false) });
        }
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: {
            available: true, high_quality_bird_crop_enabled: true, source: 'hq_candidate_full_frame'
        } });
        if (path.endsWith('.jpg') || path.endsWith('.svg')) return route.fulfill({ contentType: 'image/svg+xml', body:
            '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="600"><rect width="1000" height="600" fill="#64748b"/></svg>' });
        if (path.startsWith('/api/audio/context/') || path === '/api/species/search' || path.includes('/conversation') || path.endsWith('/species')) {
            return route.fulfill({ json: [] });
        }
        if (path.endsWith('/classifier/status')) return route.fulfill({ json: { ready: true } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/snapshot-candidates-race.html', { waitUntil: 'domcontentloaded' });
    await expect.poll(() => fixture.held !== null).toBe(true);
    return fixture;
}

async function currentA(page: Page, fixture: CandidateFixture): Promise<void> {
    await page.evaluate(() => window.snapshotRace?.setCapture('B'));
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await page.evaluate(() => window.snapshotRace?.setCapture('A'));
    await expect.poll(() => fixture.requestsA).toBe(2);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
}

async function release(fixture: CandidateFixture, fail: boolean): Promise<void> {
    const held = fixture.held;
    if (!held) throw new Error('First A candidate request was not captured');
    await held.fulfill(fail ? { status: 503, json: { detail: 'Old read failed' } } : { json: candidateResponse('A', true) });
}

for (const failure of [false, true]) {
    test(`an old A ${failure ? 'failure' : 'success'} cannot replace the new A reading after A to B to A`, async ({ page }, testInfo) => {
        // Actual modal and loader; only HTTP/prop fixtures. The first request predates the active A instance.
        const fixture = await open(page);
        await currentA(page, fixture);
        await release(fixture, failure);
        await page.waitForTimeout(150);
        await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
        await expect(page.locator('[data-counted-bird-list]')).not.toContainText('Stale first A bird');
        await expect(page.locator('[data-counted-birds-state="error"]')).toHaveCount(0);
        expect(fixture.errors).toEqual([]);
        await page.screenshot({ path: testInfo.outputPath(`aba-${failure ? 'failure' : 'success'}.png`), fullPage: true });
    });
}

test('an old owner candidate read cannot replace the fresh reading after sign-out and sign-in', async ({ page }, testInfo) => {
    const fixture = await open(page);
    await page.evaluate(() => window.snapshotRace?.setOwner(false));
    await expect(page.locator('[data-counted-birds]')).toHaveCount(0);
    await page.evaluate(() => window.snapshotRace?.setOwner(true));
    await expect.poll(() => fixture.requestsA).toBe(2);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await release(fixture, false);
    await page.waitForTimeout(150);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await expect(page.locator('[data-counted-bird-list]')).not.toContainText('Stale first A bird');
    expect(fixture.errors).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('owner-transition.png'), fullPage: true });
});


test('a fresh summary reloads an open capture without discarding its focused bird while waiting', async ({ page }, testInfo) => {
    const fixture = await open(page);
    await release(fixture, false);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    const firstBird = page.locator('[data-counted-bird-row="1"] [data-counted-bird-select]');
    await firstBird.focus();
    fixture.holdRefresh = true;
    await page.evaluate(() => window.snapshotRace?.setSummary(2));
    await expect.poll(() => fixture.heldRefresh !== null).toBe(true);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    await expect(firstBird).toBeFocused();
    const refresh = fixture.heldRefresh;
    if (!refresh) throw new Error('Summary refresh was not captured');
    await refresh.fulfill({ json: candidateResponse('A', false) });
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await expect(firstBird).toBeFocused();
    expect(fixture.errors).toEqual([]);
    await page.screenshot({ path: testInfo.outputPath('summary-refresh-focus.png'), fullPage: true });
});
