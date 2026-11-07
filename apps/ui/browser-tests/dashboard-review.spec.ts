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
