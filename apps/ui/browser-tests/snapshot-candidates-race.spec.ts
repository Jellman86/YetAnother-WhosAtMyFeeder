import { test, expect, type Page, type Route } from '@playwright/test';

/** A second, unchosen photo choice the owner can remove; absent unless a test offers it. */
type OtherChoice = 'absent' | 'shown' | 'removed';

function candidateResponse(eventId: string, stale: boolean, other: OtherChoice = 'absent') {
    const scene = `${eventId}__full_frame__f150__fixture`;
    const choices = other === 'absent' ? [] : [{ candidate_id: `${eventId}__model_crop__f20__fixture`, source_mode: 'model_crop',
        clip_variant: 'event', frame_index: 20, ranking_score: 0.5, selected: false, snapshot_source: 'hq_candidate_model_crop',
        photo_hidden: other === 'removed', image_url: '/api/race-crop.svg', thumbnail_url: '/api/race-crop.svg' }];
    return {
        event_id: eventId, current_source: 'hq_candidate_full_frame', current_candidate_id: scene,
        candidates: [{ candidate_id: scene, source_mode: 'full_frame', clip_variant: 'event', frame_index: 150,
            ranking_score: 0.9, selected: true, snapshot_source: 'hq_candidate_full_frame', image_url: '/api/race-scene.svg' }, ...choices],
        birds: Array.from({ length: stale ? 1 : 2 }, (_, index) => ({
            id: index + 1, bird_index: index, candidate_id: `${scene}__observed__${index}`, clip_variant: 'event', frame_index: 150,
            crop_box: [100 + index * 300, 100, 250 + index * 300, 250], detector_confidence: 0.8,
            species: stale ? 'Stale first A bird' : 'Current capture bird', classifier_label: 'Fixture bird', classifier_score: 0.9,
            manual_species: false, is_hidden: false, is_unknown: false
        }))
    };
}

interface CandidateFixture {
    held: Route | null;
    heldRefresh: Route | null;
    holdRefresh: boolean;
    requestsA: number;
    errors: string[];
    other: OtherChoice;
    originalAvailable: boolean;
}

test('regenerate snapshots announces recounting and refreshes the counted frame', async ({ page }) => {
    const fixture = await open(page);
    await release(fixture, false);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    const regeneration: { route: Route | null } = { route: null };
    await page.route(url => url.pathname.endsWith('/snapshot/hq-bird-crop'), route => {
        expect(route.request().method()).toBe('POST');
        expect(new URL(route.request().url()).searchParams.get('regenerate')).toBe('true');
        regeneration.route = route;
    });
    const button = page.getByRole('button', { name: 'Regenerate snapshots and recount birds', exact: true });
    await button.click();
    await expect(button).toBeDisabled();
    await expect(page.locator('[data-counted-birds-state="recounting"]')).toBeVisible();
    await expect.poll(() => regeneration.route !== null).toBe(true);
    if (!regeneration.route) throw new Error('Regeneration request was not captured');
    await regeneration.route.fulfill({ json: {
        status: 'generated_hq_bird_crop', result: 'bird_crop_replaced', high_quality_bird_crop_enabled: true
    } });
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await expect(page.locator('[data-counted-birds-state="recounting"]')).toHaveCount(0);
    await expect(button).toBeEnabled();
    expect(fixture.errors).toEqual([]);
});

test('completed reclassification refreshes an open record even when its species and bird count do not change', async ({ page }) => {
    const fixture = await open(page);
    await release(fixture, false);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    await page.evaluate(() => window.snapshotRace?.completeAnalysis());
    await expect.poll(() => fixture.requestsA).toBe(2);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    expect(fixture.errors).toEqual([]);
});

test('progress ticks and another record finishing do not reread the open record until it finishes', async ({ page }) => {
    const fixture = await open(page);
    await release(fixture, false);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('1');
    const photograph = page.locator('img[alt="Capture A"]').first();
    const firstPhoto = await photograph.getAttribute('src');
    await page.evaluate(() => {
        window.snapshotRace?.progressAnalysis(12);
        window.snapshotRace?.completeAnalysis('B');
    });
    await page.waitForTimeout(150);
    expect(fixture.requestsA).toBe(1);
    expect(await photograph.getAttribute('src')).toBe(firstPhoto);
    await page.evaluate(() => window.snapshotRace?.completeAnalysis());
    await expect.poll(() => fixture.requestsA).toBe(2);
    await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
    await expect.poll(() => photograph.getAttribute('src')).not.toBe(firstPhoto);
    expect(fixture.errors).toEqual([]);
});

async function open(page: Page, other: OtherChoice = 'absent', originalAvailable = false): Promise<CandidateFixture> {
    const fixture: CandidateFixture = {
        held: null,
        heldRefresh: null,
        holdRefresh: false,
        requestsA: 0,
        errors: [],
        other,
        originalAvailable
    };
    page.on('pageerror', error => fixture.errors.push(error.message));
    // Isolate the HTTP/prop race from a late external stylesheet applying after the modal
    // mounts. The actual application fonts are checked separately against Quark.
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        const match = /^\/api\/frigate\/(A|B)\/snapshot\/candidates$/.exec(path);
        if (match) {
            if (match[1] === 'A') {
                fixture.requestsA += 1;
                if (fixture.requestsA === 1) { fixture.held = route; return; }
                if (fixture.holdRefresh) { fixture.heldRefresh = route; return; }
            }
            return route.fulfill({ json: candidateResponse(match[1], false, fixture.other) });
        }
        const removal = /^\/api\/frigate\/A\/snapshot\/candidates\/([^/]+)$/.exec(path);
        if (removal && route.request().method() === 'PATCH') {
            const candidateId = decodeURIComponent(removal[1]);
            fixture.other = (route.request().postDataJSON() as { dismissed: boolean }).dismissed ? 'removed' : 'shown';
            return route.fulfill({ json: {
                ...candidateResponse('A', false, fixture.other),
                changed_dismissals: [{ candidate_id: candidateId, content_identity: 'fixture-pixels' }]
            } });
        }
        if (path.endsWith('/snapshot/status')) return route.fulfill({ json: {
            available: true,
            high_quality_bird_crop_enabled: true,
            source: 'hq_candidate_full_frame',
            ...(fixture.originalAvailable ? { original_frigate_snapshot_available: true } : {})
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

test('applying a photo refreshes its own capture after switching records', async ({ page }) => {
    const fixture = await open(page, 'shown', true);
    await release(fixture, false);
    const apply: { route: Route | null } = { route: null };
    await page.route('**/api/frigate/A/snapshot/apply', route => { apply.route = route; });
    const triggers = page.locator('[data-frame-strip] button[aria-pressed]');
    await triggers.nth(1).click();
    await page.getByRole('button', { name: 'Use this frame' }).click();
    await expect.poll(() => apply.route !== null).toBe(true);

    await page.evaluate(() => window.snapshotRace?.setCapture('B'));
    await expect(page.locator('img[alt="Capture B"]').first()).toBeVisible();
    // A's photo change in flight is not B's: B's own photo controls stay usable.
    await expect(regenerateButton(page)).toBeEnabled();
    if (!apply.route) throw new Error('Apply request was not captured');
    await apply.route.fulfill({ json: {
        source: 'hq_candidate_model_crop',
        applied_candidate_id: 'A__model_crop__f20__fixture',
        available: true
    } });

    await expect.poll(() => page.evaluate(() => window.snapshotRace?.mediaVersion('A'))).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.snapshotRace?.mediaVersion('B'))).toBe(0);
    await expect(page.locator('img[alt="Capture B"]').first()).toBeVisible();
    // A success that finishes after a switch stays silent: it is not news about the open record.
    expect(await toasts(page)).toEqual([]);
    await expect(regenerateButton(page)).toBeEnabled();
    expect(fixture.errors).toEqual([]);
});

test('a photo request that fails after switching records names the record it was for', async ({ page }) => {
    const fixture = await open(page, 'shown', true);
    await release(fixture, false);
    const requests: Record<'apply' | 'regenerate' | 'remove', Route | null> = { apply: null, regenerate: null, remove: null };
    await page.route('**/api/frigate/A/snapshot/apply', route => { requests.apply = route; });
    await page.route('**/api/frigate/A/snapshot/hq-bird-crop**', route => { requests.regenerate = route; });
    await page.route(url => /^\/api\/frigate\/A\/snapshot\/candidates\/[^/]+$/.test(url.pathname), route => {
        if (route.request().method() !== 'PATCH') return route.fallback();
        requests.remove = route;
    });
    const triggers = page.locator('[data-frame-strip] button[aria-pressed]');
    const failures: [keyof typeof requests, string][] = [
        ['remove', 'Fixture removal refused'],
        ['regenerate', 'Fixture regeneration refused'],
        ['apply', 'Fixture apply refused']
    ];
    for (const [index, [kind, detail]] of failures.entries()) {
        if (index > 0) {
            const requestsBefore = fixture.requestsA;
            await page.evaluate(() => window.snapshotRace?.setCapture('A'));
            await expect.poll(() => fixture.requestsA).toBeGreaterThan(requestsBefore);
        }
        await expect(page.locator('img[alt="Capture A"]').first()).toBeVisible();
        await expect(triggers).toHaveCount(3);
        if (kind === 'regenerate') {
            await regenerateButton(page).click();
        } else {
            await triggers.nth(1).click();
            const panel = page.locator('[data-frame-strip-panel]');
            await (kind === 'apply' ? page.getByRole('button', { name: 'Use this frame' }) : panel.getByRole('button', { name: 'Remove photo choice' })).click();
        }
        await expect.poll(() => requests[kind] !== null).toBe(true);
        await page.evaluate(() => window.snapshotRace?.setCapture('B'));
        await expect(page.locator('img[alt="Capture B"]').first()).toBeVisible();
        await requests[kind]?.fulfill({ status: 409, json: { detail: detail } });
        await expect.poll(async () => (await toasts(page)).find(toast => toast.message.includes(detail))).toBeTruthy();
        const toast = (await toasts(page)).find(item => item.message.includes(detail));
        expect(toast?.type).toBe('error');
        expect(toast?.message).toContain('The photo of Capture A at ');
        expect(toast?.message).not.toContain('Capture B');
    }
    expect(fixture.errors).toEqual([]);
});

test('regenerating a photo refreshes its own capture after switching records', async ({ page }) => {
    const fixture = await open(page);
    await release(fixture, false);
    const regeneration: { route: Route | null } = { route: null };
    await page.route('**/api/frigate/A/snapshot/hq-bird-crop**', route => { regeneration.route = route; });
    await regenerateButton(page).click();
    await expect.poll(() => regeneration.route !== null).toBe(true);
    await expect(page.locator('[data-counted-birds-state="recounting"]')).toBeVisible();

    await page.evaluate(() => window.snapshotRace?.setCapture('B'));
    await expect(page.locator('img[alt="Capture B"]').first()).toBeVisible();
    // B is not being recounted, so it neither says so nor locks its own button.
    await expect(page.locator('[data-counted-birds-state="recounting"]')).toHaveCount(0);
    await expect(regenerateButton(page)).toBeEnabled();
    if (!regeneration.route) throw new Error('Regeneration request was not captured');
    await regeneration.route.fulfill({ json: {
        status: 'generated_hq_bird_crop', result: 'bird_crop_replaced', high_quality_bird_crop_enabled: true
    } });

    await expect.poll(() => page.evaluate(() => window.snapshotRace?.mediaVersion('A'))).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.snapshotRace?.mediaVersion('B'))).toBe(0);
    await expect(regenerateButton(page)).toBeEnabled();
    expect(fixture.errors).toEqual([]);
});

test('a photo removal that finishes after switching records leaves the next record usable', async ({ page }) => {
    const fixture = await open(page, 'shown', true);
    await release(fixture, false);
    const removal: { route: Route | null } = { route: null };
    await page.route(url => /^\/api\/frigate\/A\/snapshot\/candidates\/[^/]+$/.test(url.pathname), route => {
        if (route.request().method() !== 'PATCH') return route.fallback();
        removal.route = route;
    });
    const triggers = page.locator('[data-frame-strip] button[aria-pressed]');
    await triggers.nth(1).click();
    await page.locator('[data-frame-strip-panel]').getByRole('button', { name: 'Remove photo choice' }).click();
    await expect.poll(() => removal.route !== null).toBe(true);

    await page.evaluate(() => window.snapshotRace?.setCapture('B'));
    await expect(page.locator('img[alt="Capture B"]').first()).toBeVisible();
    await expect(regenerateButton(page)).toBeEnabled();
    if (!removal.route) throw new Error('Removal request was not captured');
    await removal.route.fulfill({ json: {
        ...candidateResponse('A', false, 'removed'),
        changed_dismissals: [{ candidate_id: 'A__model_crop__f20__fixture', content_identity: 'fixture-pixels' }]
    } });

    await page.waitForTimeout(150);
    await expect(regenerateButton(page)).toBeEnabled();
    await expect(triggers).toHaveCount(3);
    expect(fixture.errors).toEqual([]);
});

async function toasts(page: Page): Promise<{ type: string; message: string }[]> {
    return (await page.evaluate(() => window.snapshotRace?.toasts())) ?? [];
}

function regenerateButton(page: Page) {
    return page.getByRole('button', { name: 'Regenerate snapshots and recount birds', exact: true });
}

async function release(fixture: CandidateFixture, fail: boolean): Promise<void> {
    const held = fixture.held;
    if (!held) throw new Error('First A candidate request was not captured');
    await held.fulfill(fail ? { status: 503, json: { detail: 'Old read failed' } } : { json: candidateResponse('A', true, fixture.other) });
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

for (const refreshFailed of [false, true]) {
    test(`a candidate read sent before a photo removal (${refreshFailed ? '503 failure' : '200 success'}) preserves removed and chosen photo state (#1107)`, async ({ page }) => {
        const fixture = await open(page, 'shown', true);
        await release(fixture, false);
        const triggers = page.locator('[data-frame-strip] button[aria-pressed]');
        // Camera snapshot + removable crop + chosen scene.
        await expect(triggers).toHaveCount(3);
        await expect(triggers.nth(2)).toHaveAttribute('aria-pressed', 'true');
        fixture.holdRefresh = true;
        await page.evaluate(() => window.snapshotRace?.setSummary(2));
        await expect.poll(() => fixture.heldRefresh !== null).toBe(true);

        // Remove the middle choice (the removable crop).
        await triggers.nth(1).click();
        await page.locator('[data-frame-strip-panel]').getByRole('button', { name: 'Remove photo choice' }).click();
        await expect(triggers).toHaveCount(2);
        await expect(triggers.nth(1)).toHaveAttribute('aria-pressed', 'true');
        const refresh = fixture.heldRefresh;
        if (!refresh) throw new Error('Refresh read was not captured');
        if (refreshFailed) {
            await refresh.fulfill({ status: 503, json: { detail: 'Stale refresh failed' } });
        } else {
            // The read left before the removal, so it still lists the removed photo and an older current candidate.
            await refresh.fulfill({ json: { ...candidateResponse('A', false, 'shown'), current_candidate_id: null, current_source: 'frigate_snapshot' } });
        }

        if (!refreshFailed) {
            await expect(page.locator('[data-counted-birds-total]')).toHaveText('2');
        }
        await page.waitForTimeout(150);
        // Camera snapshot and chosen scene stay intact; removed crop stays gone; Undo and chosen mark survive.
        await expect(triggers).toHaveCount(2);
        await expect(triggers.nth(1)).toHaveAttribute('aria-pressed', 'true');
        await expect(page.getByRole('button', { name: 'Undo', exact: true })).toBeVisible();
        await expect(page.getByRole('button', { name: 'Regenerate snapshots and recount birds', exact: true })).toBeEnabled();
        expect(fixture.errors).toEqual([]);
    });
}
