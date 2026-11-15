import { expect, test } from '@playwright/test';

// The range check read and found nothing, so "Nothing waiting" rests on the visits alone.
const noSpeciesChecks = { span: 'day', window_start: new Date(Date.now() - 86400000).toISOString(), window_end: new Date().toISOString(), nearby_check: 'checked', species: [] };

test('accepted historical choice survives an older pending count and omission from fresh history', async ({ page }) => {
    const record = { frigate_event: 'historical-choice', display_name: 'Dunnock', category_name: 'Dunnock', camera_name: 'birdcam',
        detection_time: new Date(Date.now() - 48 * 3600000).toISOString(), score: .98, manual_tagged: false,
        classification_input: { source: 'full_frame', is_cropped: false } };
    let historyReads = 0;
    let countWaiting = false;
    let releaseCount: () => void = () => undefined;
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path === '/api/events' && request.method() === 'GET') {
            historyReads++;
            return route.fulfill({ json: historyReads <= 2 ? [record] : [] });
        }
        if (path === '/api/events/count') {
            if (!countWaiting) {
                countWaiting = true;
                await new Promise<void>(resolve => { releaseCount = resolve; });
            }
            return route.fulfill({ json: { count: 0 } });
        }
        if (path === '/api/events/historical-choice' && request.method() === 'PATCH') {
            return route.fulfill({ json: { status: 'unchanged', event_id: record.frigate_event, new_species: 'Dunnock', category_name: 'Dunnock', manual_tagged: true } });
        }
        if (path === '/api/events/review-queue') return route.fulfill({ json: { items: [{ event: record, reason: 'new_species', species_sightings: 1 }], total: 1 } });
        if (path === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
        if (/\/snapshot(?:\/thumbnail)?$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });
    await page.goto('/browser-tests/dashboard-review.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-count]')).toHaveText('1');
    await page.evaluate(() => window.dispatchEvent(new Event('test-history-refresh')));
    await expect.poll(() => countWaiting).toBe(true);
    await card.getByRole('button', { name: 'Work through the queue' }).click();
    const modal = page.locator('[data-review-queue-modal]');
    await modal.getByRole('button', { name: 'Confirm Dunnock', exact: true }).click();
    await expect(modal.getByRole('heading', { name: 'Queue clear' })).toBeVisible();
    await modal.getByRole('button', { name: 'Back to the dashboard' }).click();
    releaseCount();
    await expect.poll(() => historyReads).toBeGreaterThanOrEqual(3);
    await expect(card.locator('[data-review-queue-count]')).toHaveCount(0);
    await expect(card.getByText('Every visit in the last 24 hours has a species. Nothing waiting on you.')).toBeVisible();
});

for (const { fails, ageHours } of [{ fails: false, ageHours: 0 }, { fails: true, ageHours: 0 }, { fails: false, ageHours: 48 }]) {
    test(`dashboard queue ${fails ? 'keeps a failed decision pending' : 'clears saved whole-view choices without refresh or SSE'} at ${ageHours} hours old`, async ({ page }) => {
        const records = ['Dunnock', 'European Robin'].map((name, index) => ({
            frigate_event: `review-${index}`, display_name: name, common_name: name,
            category_name: name, camera_name: 'birdcam',
            detection_time: new Date(Date.now() - ageHours * 3600000 - (index + 1) * 60000).toISOString(),
            score: 0.98, manual_tagged: false,
            classification_input: { source: 'recording_frame', is_cropped: false },
            initial_classification_input: { source: 'recording_frame', is_cropped: false }
        }));
        const writes: string[] = [];
        let queueReads = 0;
        await page.route(url => url.pathname.startsWith('/api/'), route => {
            const request = route.request();
            const path = new URL(request.url()).pathname;
            if (request.method() === 'PATCH' && path.startsWith('/api/events/')) {
                const id = path.split('/').at(-1) ?? '';
                writes.push(id);
                if (fails) return route.fulfill({ status: 503, json: { detail: 'Could not save this decision.' } });
                const record = records.find(item => item.frigate_event === id);
                return route.fulfill({ json: { status: 'unchanged', event_id: id, new_species: record?.display_name, category_name: record?.category_name, manual_tagged: true } });
            }
            if (path === '/api/events') return route.fulfill({ json: records });
            // Deliberately keep returning the pre-review projection, including after a save.
            if (path === '/api/events/review-queue') {
                queueReads++;
                return route.fulfill({ json: { items: records.map(event => ({ event, reason: 'new_species', species_sightings: 1 })), total: records.length } });
            }
            if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
            if (/\/snapshot(?:\/thumbnail)?$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
            if (path === '/api/species/feeder') return route.fulfill({ json: [] });
            if (path === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
            // Supporting dashboard readings are unavailable; the ready review history remains usable.
            return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
        });
        await page.goto('/browser-tests/dashboard-review.html');
        const card = page.locator('[data-dashboard-review-queue]');
        await expect(card.locator('[data-review-queue-count]')).toHaveText('2');
        await card.getByRole('button', { name: 'Work through the queue' }).click();
        const modal = page.locator('[data-review-queue-modal]');
        await expect(modal).toBeVisible();
        await modal.getByRole('button', { name: 'Confirm European Robin', exact: true }).click();
        if (fails) {
            await expect(page.locator('[data-toast-container]')).toContainText('Could not save this decision.');
            await expect(modal.locator('[data-review-position]')).toHaveText('1 of 2');
            await modal.getByRole('button', { name: 'Close', exact: true }).click();
            await expect(card.locator('[data-review-queue-count]')).toHaveText('2');
            expect(writes).toEqual(['review-1']);
        } else {
            await modal.getByRole('button', { name: 'Confirm Dunnock', exact: true }).click();
            await expect(modal.getByRole('heading', { name: 'Queue clear' })).toBeVisible();
            await modal.getByRole('button', { name: 'Back to the dashboard' }).click();
            await expect.poll(() => queueReads).toBeGreaterThanOrEqual(3);
            await expect(card.locator('[data-review-queue-count]')).toHaveCount(0);
            await expect(card.getByText('Every visit in the last 24 hours has a species. Nothing waiting on you.')).toBeVisible();
            await expect(card.getByRole('button', { name: 'Work through the queue' })).toHaveCount(0);
            expect(writes).toEqual(['review-1', 'review-0']);
        }
    });
}

test('Needs your call counts what the server says is waiting, and the walkthrough reads all of it (#917)', async ({ page }) => {
    const waiting = Array.from({ length: 24 }, (_unused, index) => ({
        frigate_event: `unknown-${index}`, display_name: 'Unknown Bird', category_name: 'Unknown Bird', camera_name: 'birdcam',
        detection_time: new Date(Date.now() - (24 - index) * 1800000).toISOString(), score: 0.9, manual_tagged: false
    }));
    const limits: number[] = [];
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        // The recent history holds no sign of them: every one has been pushed off its page.
        if (url.pathname === '/api/events') return route.fulfill({ json: [] });
        if (url.pathname === '/api/events/review-queue') {
            const limit = Number(url.searchParams.get('limit'));
            limits.push(limit);
            return route.fulfill({ json: { items: waiting.slice(0, limit).map(event => ({ event, reason: 'unknown_species' })), total: waiting.length } });
        }
        if (url.pathname.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
        if (/\/snapshot(?:\/thumbnail)?$/.test(url.pathname)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
        if (url.pathname === '/api/species/feeder') return route.fulfill({ json: [] });
        if (url.pathname === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });
    await page.goto('/browser-tests/dashboard-review.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-count]')).toHaveText('24');
    await card.getByRole('button', { name: 'Work through the queue' }).click();
    const modal = page.locator('[data-review-queue-modal]');
    await expect(modal.locator('[data-review-position]')).toHaveText('1 of 24');
    expect(Math.max(...limits)).toBeGreaterThanOrEqual(24);
});

test('Needs your call says it could not check when the queue fails, never that nothing is waiting (#917)', async ({ page }) => {
    let failing = true;
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/events') return route.fulfill({ json: [] });
        if (path === '/api/events/review-queue') {
            if (failing) return route.fulfill({ status: 503, json: { detail: 'Queue unavailable.' } });
            return route.fulfill({ json: { items: [], total: 0 } });
        }
        if (path === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });
    await page.goto('/browser-tests/dashboard-review.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.getByText('The queue could not be checked, so it is not known whether anything is waiting.')).toBeVisible();
    await expect(card.getByText('Nothing waiting on you.')).toHaveCount(0);
    failing = false;
    await card.getByRole('button', { name: /try again|retry/i }).click();
    await expect(card.getByText('Every visit in the last 24 hours has a species. Nothing waiting on you.')).toBeVisible();
});

test('finishing a walkthrough that could not hold everything says more are waiting (#917)', async ({ page }) => {
    const listed = { frigate_event: 'listed', display_name: 'Unknown Bird', category_name: 'Unknown Bird', camera_name: 'birdcam',
        detection_time: new Date(Date.now() - 3600000).toISOString(), score: 0.9, manual_tagged: false };
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request(), path = new URL(request.url()).pathname;
        if (path === '/api/events') return route.fulfill({ json: [] });
        if (path === '/api/events/review-queue') return route.fulfill({ json: { items: [{ event: listed, reason: 'unknown_species' }], total: 3 } });
        if (request.method() === 'POST' && path.endsWith('/hide')) return route.fulfill({ json: { status: 'ok', event_id: listed.frigate_event, is_hidden: true } });
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
        if (/\/snapshot(?:\/thumbnail)?$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
        if (path === '/api/species/feeder') return route.fulfill({ json: [] });
        if (path === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });
    await page.goto('/browser-tests/dashboard-review.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-count]')).toHaveText('3');
    await card.getByRole('button', { name: 'Work through the queue' }).click();
    const modal = page.locator('[data-review-queue-modal]');
    await modal.getByRole('button', { name: /Skip|skip/ }).first().click();
    await expect(modal.locator('[data-review-more-waiting]')).toContainText('2 more are waiting');
    await expect(modal.getByRole('heading', { name: 'Queue clear' })).toHaveCount(0);
});


test("a visit below the naming threshold can be confirmed as the model's own species in one step", async ({ page }) => {
    const at = (minutes: number): string => new Date(Date.now() - minutes * 60000).toISOString();
    const lowScore = { frigate_event: 'review-low', display_name: 'Eurasian Bullfinch', common_name: 'Eurasian Bullfinch', category_name: 'Eurasian Bullfinch',
        camera_name: 'birdcam', detection_time: at(3), score: 0.57, manual_tagged: false, classification_input: { source: 'recording_frame', is_cropped: false } };
    const unknown = { frigate_event: 'review-unknown', display_name: 'Unknown Bird', common_name: null, category_name: 'Unknown Bird',
        camera_name: 'birdcam', detection_time: at(2), score: 0.31, manual_tagged: false, classification_input: { source: 'recording_frame', is_cropped: false } };
    const writes: Array<{ id: string; body: string }> = [];
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (request.method() === 'PATCH' && path.startsWith('/api/events/')) {
            const id = path.split('/').at(-1) ?? '';
            writes.push({ id, body: request.postData() ?? '' });
            return route.fulfill({ json: { status: 'updated', event_id: id, new_species: 'Eurasian Bullfinch', category_name: 'Eurasian Bullfinch', manual_tagged: true } });
        }
        if (path === '/api/events') return route.fulfill({ json: [lowScore, unknown] });
        if (path === '/api/events/review-queue') {
            return route.fulfill({ json: { items: [{ event: lowScore, reason: 'low_score' }, { event: unknown, reason: 'unknown_species' }], total: 2 } });
        }
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
        if (/\/snapshot(?:\/thumbnail)?$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
        if (path === '/api/species/feeder') return route.fulfill({ json: [] });
        if (path === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });
    await page.goto('/browser-tests/dashboard-review.html');
    const card = page.locator('[data-dashboard-review-queue]');
    await expect(card.locator('[data-review-queue-count]')).toHaveText('2');
    await card.getByRole('button', { name: 'Work through the queue' }).click();
    const modal = page.locator('[data-review-queue-modal]');
    const confirm = modal.getByRole('button', { name: 'Confirm Eurasian Bullfinch', exact: true });
    await expect(confirm).toBeVisible();
    await confirm.click();
    await expect.poll(() => writes.map(write => write.id)).toEqual(['review-low']);
    expect(writes[0].body).toContain('Eurasian Bullfinch');
    // A visit with no species has nothing to confirm; the owner picks one or hides it.
    await expect(modal.locator('[data-review-position]')).toHaveText('2 of 2');
    await expect(modal.getByRole('button', { name: /^Confirm / })).toHaveCount(0);
});

test('a confirm taken on a visit someone else has since corrected is refused, and the row shows what it says now', async ({ context }) => {
    // One server, two owners' tabs. Its PATCH applies a decision only while the visit still carries
    // the identification the tab was shown, as the backend does.
    const visit = { frigate_event: 'review-race', display_name: 'Eurasian Bullfinch', common_name: 'Eurasian Bullfinch', category_name: 'Pyrrhula pyrrhula',
        scientific_name: 'Pyrrhula pyrrhula', camera_name: 'birdcam', detection_time: new Date(Date.now() - 180000).toISOString(), score: 0.57,
        manual_tagged: false, classification_input: { source: 'recording_frame', is_cropped: false } };
    const chaffinch = { id: 'Fringilla coelebs', display_name: 'Fringilla coelebs', scientific_name: 'Fringilla coelebs', common_name: 'Common Chaffinch' };
    const stored = { ...visit };
    const writes: Array<{ expected: unknown; status: number }> = [];
    await context.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (request.method() === 'PATCH' && path === '/api/events/review-race') {
            const body = request.postDataJSON() as { display_name: string; expected_category_name?: string };
            if (body.expected_category_name !== undefined && body.expected_category_name.toLowerCase() !== stored.category_name.toLowerCase()) {
                writes.push({ expected: body.expected_category_name, status: 409 });
                return route.fulfill({ status: 409, json: { detail: {
                    code: 'identification_changed',
                    message: `This visit was changed elsewhere. It now reads ${stored.display_name}.`,
                    current: { display_name: stored.display_name, category_name: stored.category_name, scientific_name: stored.scientific_name, common_name: stored.common_name, manual_tagged: stored.manual_tagged }
                } } });
            }
            writes.push({ expected: body.expected_category_name, status: 200 });
            const picked = body.display_name === chaffinch.id ? { display_name: 'Common Chaffinch', category_name: chaffinch.id, scientific_name: chaffinch.id, common_name: 'Common Chaffinch' } : {};
            Object.assign(stored, picked, { manual_tagged: true });
            return route.fulfill({ json: { status: 'updated', event_id: visit.frigate_event, new_species: stored.display_name, category_name: stored.category_name, scientific_name: stored.scientific_name, common_name: stored.common_name, manual_tagged: true } });
        }
        if (path === '/api/events') return route.fulfill({ json: [visit] });
        if (path === '/api/events/review-queue') return route.fulfill({ json: { items: [{ event: visit, reason: 'low_score' }], total: 1 } });
        if (path === '/api/species/search') return route.fulfill({ json: [chaffinch] });
        if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
        if (/\/snapshot(?:\/thumbnail)?$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
        if (path === '/api/leaderboard/species') return route.fulfill({ json: noSpeciesChecks });
        return route.fulfill({ status: 503, json: { detail: 'Supporting fixture reading unavailable.' } });
    });

    // Both tabs open the queue on the same snapshot of the visit.
    const first = await context.newPage();
    const second = await context.newPage();
    for (const page of [first, second]) {
        await page.goto('/browser-tests/dashboard-review.html');
        await page.locator('[data-dashboard-review-queue]').getByRole('button', { name: 'Work through the queue' }).click();
        await expect(page.locator('[data-review-queue-modal]').getByRole('button', { name: 'Confirm Eurasian Bullfinch', exact: true })).toBeVisible();
    }

    // The first tab corrects it to Common Chaffinch.
    await first.locator('[data-review-queue-modal]').getByRole('button', { name: /^Common Chaffinch .*Identify$/ }).click();
    await expect.poll(() => writes).toEqual([{ expected: 'Pyrrhula pyrrhula', status: 200 }]);

    // The second tab, still showing the old snapshot, confirms the old species: refused.
    const modal = second.locator('[data-review-queue-modal]');
    await modal.getByRole('button', { name: 'Confirm Eurasian Bullfinch', exact: true }).click();
    await expect.poll(() => writes.at(-1)).toEqual({ expected: 'Pyrrhula pyrrhula', status: 409 });
    await expect(second.locator('[data-toast-container]')).toContainText('This visit was changed elsewhere. It now reads Common Chaffinch.');
    // The row now shows what it says, and the newer correction stands.
    await expect(modal.getByRole('button', { name: 'Confirm Eurasian Bullfinch', exact: true })).toHaveCount(0);
    await expect(modal).toContainText('Common Chaffinch');
    await expect(modal.locator('[data-review-position]')).toHaveText('1 of 1');
    expect(stored.category_name).toBe('Fringilla coelebs');
});
