import { test, expect, type Page } from '@playwright/test';

// Add observation: the time a file was taken, a file uploaded twice, and the species search.

const draftId = 'd'.repeat(32);
const savedEventId = `manual_${'e'.repeat(32)}`;
const goldcrest = { id: 'Regulus regulus', display_name: 'Regulus regulus', scientific_name: 'Regulus regulus', common_name: 'Goldcrest' };
const photo = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="240"><rect width="320" height="240" fill="#334155"/></svg>';

function draft(overrides: Record<string, unknown> = {}) {
    return {
        id: draftId, status: 'ready', media_type: 'image', original_filename: 'robin.jpg', content_type: 'image/jpeg',
        content_sha256: 'a'.repeat(64), size_bytes: 1024, progress_current: 1, progress_total: 1, progress_percent: 100,
        predictions: [{ label: 'Erithacus rubecula', score: 0.91, common_name: 'European Robin', scientific_name: 'Erithacus rubecula' }],
        captured_at: null, captured_at_source: 'none', latitude: null, longitude: null, location_source: null,
        preview_url: `/api/manual-observations/${draftId}/preview`, media_url: `/api/manual-observations/${draftId}/media`,
        ...overrides
    };
}

interface Serve {
    upload?: { status: number; json: unknown };
    ready?: Record<string, unknown>;
    search?: (query: string) => unknown[];
}

async function serve(page: Page, options: Serve): Promise<{ confirmed: Record<string, unknown>[] }> {
    const calls = { confirmed: [] as Record<string, unknown>[] };
    // Map tiles and fonts are not part of what is under test.
    await page.route(url => url.hostname !== '127.0.0.1', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/manual-observations' && request.method() === 'POST') {
            const reply = options.upload ?? { status: 202, json: draft({ status: 'queued', progress_percent: 0 }) };
            return route.fulfill({ status: reply.status, json: reply.json });
        }
        if (path.endsWith('/preview')) return route.fulfill({ contentType: 'image/svg+xml', body: photo });
        if (path.endsWith('/confirm')) {
            calls.confirmed.push(request.postDataJSON() as Record<string, unknown>);
            return route.fulfill({ json: { status: 'saved', event_id: savedEventId, detection_url: `/events?event=${savedEventId}` } });
        }
        if (path === `/api/manual-observations/${draftId}`) return route.fulfill({ json: draft(options.ready) });
        if (path === '/api/species/search') {
            const query = new URL(request.url()).searchParams.get('q') ?? '';
            return route.fulfill({ json: options.search ? options.search(query) : [] });
        }
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/manual-observation.html');
    return calls;
}

async function uploadAndReview(page: Page) {
    await page.locator('input[type="file"]').setInputFiles({ name: 'robin.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('jpeg') });
    await page.getByRole('button', { name: 'Upload and analyse' }).click();
    await expect(page.getByRole('radio', { name: /European Robin/ })).toBeChecked();
}

test('a photo with a capture time prefills Observed at and says it came from the photo', async ({ page }) => {
    const calls = await serve(page, { ready: { captured_at: '2026-05-01T06:15:30Z', captured_at_source: 'exif' } });
    await uploadAndReview(page);

    const observedAt = page.getByLabel('Observed at');
    // The fixture browser runs in Europe/London, which is on summer time in May.
    await expect(observedAt).toHaveValue('2026-05-01T07:15:30');
    const chip = page.locator('[data-manual-observation-time-source]');
    await expect(chip).toHaveText('From the photo');
    await expect(page.locator('#manual-observation-when-help')).toContainText("Read from the photo's own metadata");

    await page.getByRole('button', { name: 'Add European Robin' }).click();
    await expect.poll(() => calls.confirmed.length).toBe(1);
    expect(calls.confirmed[0].observed_at).toBe('2026-05-01T06:15:30.000Z');
});

test('editing the prefilled time drops the claim that it came from the photo', async ({ page }) => {
    await serve(page, { ready: { captured_at: '2026-05-01T06:15:30Z', captured_at_source: 'exif' } });
    await uploadAndReview(page);

    await page.getByLabel('Observed at').fill('2026-05-02T09:00');
    await expect(page.locator('[data-manual-observation-time-source]')).toHaveCount(0);
    await page.getByLabel('Observed at').fill('');
    await expect(page.locator('#manual-observation-when-help')).toHaveText('Leave empty to use the time saved in the file.');
});

test('a file without a capture time leaves the field empty and says the save time is used', async ({ page }) => {
    const calls = await serve(page, {});
    await uploadAndReview(page);

    await expect(page.getByLabel('Observed at')).toHaveValue('');
    await expect(page.locator('[data-manual-observation-time-source]')).toHaveCount(0);
    await expect(page.locator('#manual-observation-when-help')).toHaveText('No capture time was found in the file. Leave empty to use the time you save it.');
    await page.getByRole('button', { name: 'Add European Robin' }).click();
    await expect.poll(() => calls.confirmed.length).toBe(1);
    expect(calls.confirmed[0].observed_at).toBeNull();
});

test('uploading a saved file again offers the saved observation', async ({ page }) => {
    await serve(page, { upload: { status: 409, json: { detail: { message: 'This media has already been uploaded.', draft_id: draftId, event_id: savedEventId } } } });
    await page.locator('input[type="file"]').setInputFiles({ name: 'robin.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('jpeg') });
    await page.getByRole('button', { name: 'Upload and analyse' }).click();

    await expect(page.getByRole('alert')).toContainText('This file is already saved as an observation.');
    await page.getByRole('button', { name: 'Open the saved observation' }).click();
    await expect(page.locator('[data-fixture-navigated]')).toHaveText(`/events?event=${savedEventId}`);
});

test('uploading a file that is still a draft continues that review', async ({ page }) => {
    await serve(page, { upload: { status: 409, json: { detail: { message: 'This media has already been uploaded.', draft_id: draftId, event_id: null } } } });
    await page.locator('input[type="file"]').setInputFiles({ name: 'robin.jpg', mimeType: 'image/jpeg', buffer: Buffer.from('jpeg') });
    await page.getByRole('button', { name: 'Upload and analyse' }).click();

    await expect(page.getByRole('alert')).toContainText('still waiting for your review');
    await page.getByRole('button', { name: 'Continue that review' }).click();
    await expect(page.getByRole('radio', { name: /European Robin/ })).toBeChecked();
    await expect(page.getByRole('alert')).toHaveCount(0);
});

test('the species field searches common and scientific names and warns about unknown species', async ({ page }) => {
    const calls = await serve(page, { search: query => (/goldcrest|regulus/i.test(query) ? [goldcrest] : []) });
    await uploadAndReview(page);

    const species = page.getByRole('searchbox', { name: 'Species', exact: true });
    await species.fill('Goldcrest');
    await page.getByRole('button', { name: 'Goldcrest Regulus regulus' }).click();
    await expect(page.locator('#manual-observation-species-help')).toHaveText('Goldcrest · Regulus regulus');
    await expect(page.locator('[data-manual-observation-species-unknown]')).toHaveCount(0);

    await species.fill('Purple Feeder Dragon');
    await expect(page.locator('[data-manual-observation-species-unknown]')).toHaveText('Not a species this model knows; it will be saved as typed.');

    await species.fill('Goldcrest');
    await page.getByRole('button', { name: 'Goldcrest Regulus regulus' }).click();
    await page.getByRole('button', { name: 'Add Goldcrest' }).click();
    await expect.poll(() => calls.confirmed.length).toBe(1);
    expect(calls.confirmed[0].label).toBe('Regulus regulus');
    expect(calls.confirmed[0].camera_name).toBe('Manual upload');
});

test('the phone step pills keep their names for screen readers', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 800 });
    await serve(page, {});
    const steps = page.getByRole('list', { name: 'Observation progress' });
    for (const name of ['Upload', 'Analyse', 'Review', 'Save']) {
        // Visually hidden, not display:none, so the step is still named.
        const title = steps.getByText(name, { exact: true });
        expect(await title.evaluate(node => getComputedStyle(node).display)).not.toBe('none');
    }
    await expect(steps.getByText('1', { exact: true })).toBeVisible();
    const box = await page.getByRole('button', { name: 'Upload and analyse' }).boundingBox();
    expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
});
