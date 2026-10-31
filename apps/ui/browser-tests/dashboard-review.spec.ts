import { expect, test } from '@playwright/test';

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
        if (path === '/api/events/new-species') return route.fulfill({ json: { items: [{ ...record, species_sightings: 1 }] } });
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
        let newSpeciesReads = 0;
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
            if (path === '/api/events/new-species') {
                newSpeciesReads++;
                return route.fulfill({ json: { items: records.map(record => ({ ...record, species_sightings: 1 })) } });
            }
            if (path.endsWith('/snapshot/candidates')) return route.fulfill({ json: { candidates: [], birds: [] } });
            if (/\/snapshot(?:\/thumbnail)?$/.test(path)) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
            if (path === '/api/species/feeder') return route.fulfill({ json: [] });
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
            await expect.poll(() => newSpeciesReads).toBeGreaterThanOrEqual(3);
            await expect(card.locator('[data-review-queue-count]')).toHaveCount(0);
            await expect(card.getByText('Every visit in the last 24 hours has a species. Nothing waiting on you.')).toBeVisible();
            await expect(card.getByRole('button', { name: 'Work through the queue' })).toHaveCount(0);
            expect(writes).toEqual(['review-1', 'review-0']);
        }
    });
}
