import { expect, test } from '@playwright/test';

const modelStatus = { country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [{ variant: '4.0.3b', installed: true, size_bytes: 223999179 }] };

const motionStatus = { cameras: [], installed: false, catalogue_ready: true, busy: false, state: 'disabled', message: 'Motion collection is off.', interval_seconds: 120, photo_limit: 128, photo_retention_days: 3 };

const id = 'a'.repeat(32);
const row = { id, camera: 'patio', frigate_label: 'cat', observed_at: '2026-10-11T18:00:00Z', reviewed_at: null, status: 'pending', snapshot_url: `/api/garden/${id}/snapshot` };

test('owner can dismiss a false capture, restore it and review at narrow widths', async ({ page }) => {
    let status = 'pending';
    await page.route(url => url.pathname.startsWith('/api/garden'), async route => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/garden/identification') return route.fulfill({ json: modelStatus });
        if (url.pathname.endsWith('/snapshot')) return route.fulfill({ status: 404 });
        if (route.request().method() === 'POST') {
            status = url.pathname.endsWith('/dismiss') ? 'dismissed' : 'pending';
            return route.fulfill({ json: { ...row, status } });
        }
        const items = url.searchParams.get('status') === status ? [{ ...row, status }] : [];
        return route.fulfill({ json: { items, total: items.length, limit: 8, offset: 0 } });
    });
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByText('Frigate suggested: cat')).toBeVisible();
    await expect(page.getByText('Snapshot unavailable')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeDisabled();
    await page.getByRole('button', { name: 'Dismiss capture' }).click();
    await expect(page.getByText('No captures in this view')).toBeVisible();
    await page.getByRole('button', { name: 'Dismissed', exact: true }).click();
    await page.getByRole('button', { name: 'Return to review' }).click();
    await page.getByRole('button', { name: 'Needs review', exact: true }).click();
    await expect(page.getByText('Frigate suggested: cat')).toBeVisible();
    await page.setViewportSize({ width: 320, height: 740 });
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('owner confirms presence only after the photo loads', async ({ page }) => {
    let confirmed = false;
    await page.route(url => url.pathname.startsWith('/api/garden'), async route => {
        if (route.request().url().endsWith('/identification')) return route.fulfill({ json: modelStatus });
        if (route.request().url().endsWith('/snapshot')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#28594a"/></svg>' });
        if (route.request().method() === 'POST') {
            confirmed = true;
            return route.fulfill({ json: { ...row, status: 'confirmed' } });
        }
        const status = new URL(route.request().url()).searchParams.get('status');
        const items = (status === 'confirmed') === confirmed ? [{ ...row, status: confirmed ? 'confirmed' : 'pending' }] : [];
        return route.fulfill({ json: { items, total: items.length, limit: 8, offset: 0 } });
    });
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
    await page.getByRole('button', { name: 'Confirm animal present' }).click();
    await expect(page.getByText('No captures in this view')).toBeVisible();
    await page.getByRole('button', { name: 'Confirmed animals', exact: true }).click();
    await expect(page.getByText('Frigate suggested: cat')).toBeVisible();
    expect(confirmed).toBe(true);
});

test('history error is visible and refresh recovers', async ({ page }) => {
    let failed = true;
    await page.route('**/api/garden?**', route => route.fulfill(failed
        ? { status: 503, json: { detail: 'History temporarily unavailable' } }
        : { json: { items: [], total: 0, limit: 8, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('alert')).toContainText('History temporarily unavailable');
    failed = false;
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await expect(page.getByText('No captures in this view')).toBeVisible();
});

test('garden camera opt-in saves independently of a Nest bird role', async ({ page }) => {
    let settings: Record<string, unknown> = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
        mqtt_auth: false, cameras: ['patio'], camera_roles: { patio: 'nest' },
        garden_cameras: [], garden_labels: ['cat', 'dog'], classification_threshold: 0.7
    };
    let written: Record<string, unknown> | null = null;
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload: unknown = request.postDataJSON();
                if (typeof payload !== 'object' || payload === null || Array.isArray(payload)) throw new Error('Expected settings object');
                written = payload as Record<string, unknown>;
                settings = { ...settings, ...written };
                return route.fulfill({ json: { status: 'ok' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: { patio: {} } } });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    const nest = page.getByRole('button', { name: 'Nest', exact: true });
    await expect(nest).toHaveAttribute('aria-pressed', 'true');
    const garden = page.getByRole('button', { name: /Garden animals/ });
    await garden.click();
    await expect(garden).toHaveAttribute('aria-pressed', 'true');
    await expect(nest).toHaveAttribute('aria-pressed', 'true');
    await page.getByRole('button', { name: 'Collect motion review photos' }).click();
    await page.getByLabel('Frigate animal labels', { exact: true }).fill('cat, dog, squirrel');
    await page.getByRole('button', { name: /Apply Settings/i }).click();
    await expect.poll(() => written?.garden_cameras).toEqual(['patio']);
    await expect.poll(() => written?.garden_motion_cameras).toEqual(['patio']);
    await expect.poll(() => written?.camera_roles).toEqual({ patio: 'nest' });
    await expect.poll(() => written?.garden_labels).toEqual(['cat', 'dog', 'squirrel']);
});

for (const outcome of ['species', 'group', 'unknown'] as const) {
    test(`owner reviews a ${outcome} suggestion without changing animal presence`, async ({ page }) => {
        let suggestion: Record<string, unknown> | null = null;
        const actions: string[] = [];
        await page.route(url => url.pathname.startsWith('/api/garden'), async route => {
            const path = new URL(route.request().url()).pathname;
            if (path === '/api/garden/identification') return route.fulfill({ json: modelStatus });
            if (path.endsWith('/snapshot')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"><rect width="640" height="360" fill="#28594a"/></svg>' });
            if (route.request().method() === 'POST') {
                actions.push(path);
                if (path.endsWith('/identify')) {
                    expect(route.request().headers()['content-type']).toBe('application/json');
                    expect(route.request().postDataJSON()).toEqual({ variant: '4.0.3b', provider: 'cpu' });
                    suggestion = { outcome: outcome === 'unknown' ? 'unknown' : 'suggestion', review: 'unreviewed', name: outcome === 'group' ? 'canidae' : 'red fox', rank: outcome === 'group' ? 'family' : 'species', score: 0.91, variant: '4.0.3b', devices: ['CPUExecutionProvider'], country: 'GBR', input_kind: 'whole_image', box_xywh: null, frame_size: [640, 360] };
                } else if (suggestion) suggestion = { ...suggestion, review: path.endsWith('/accept') ? 'accepted' : 'dismissed' };
                return route.fulfill({ json: { ...row, status: 'confirmed', identification: suggestion } });
            }
            const items = new URL(route.request().url()).searchParams.get('status') === 'confirmed' ? [{ ...row, status: 'confirmed', identification: suggestion }] : [];
            return route.fulfill({ json: { items, total: items.length, limit: 8, offset: 0 } });
        });
        await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.goto('/browser-tests/garden.html');
        await expect(page.getByRole('button', { name: 'Confirmed animals', exact: true })).toBeEnabled();
        await page.getByRole('button', { name: 'Confirmed animals', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Suggest species', exact: true })).toBeEnabled();
        await page.getByRole('button', { name: 'Suggest species', exact: true }).click();
        if (outcome === 'unknown') {
            await expect(page.getByText(/No reliable identification/)).toBeVisible();
            await expect(page.getByRole('button', { name: 'Confirm identification', exact: true })).toHaveCount(0);
        } else {
            if (outcome === 'group') await expect(page.getByText('Animal group only; species is unresolved.')).toBeVisible();
            await page.getByRole('button', { name: 'Confirm identification', exact: true }).click();
            await expect(page.getByText('Identification confirmed by you')).toBeVisible();
            await page.getByRole('button', { name: 'Discard identification', exact: true }).click();
            await expect(page.getByText('Identification confirmed by you')).toHaveCount(0);
        }
        expect(actions.every(path => path.endsWith('/identify') || path.includes('/identification/'))).toBe(true);
        await page.getByText('Species suggestions', { exact: true }).click();
        await page.setViewportSize({ width: 320, height: 740 });
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
}

test('bird preemption is explained and does not manufacture a suggestion', async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/garden'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/garden/identification') return route.fulfill({ json: modelStatus });
        if (path.endsWith('/snapshot')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10"/>' });
        if (path.endsWith('/identify')) return route.fulfill({ status: 409, json: { detail: 'Bird inference needs the hardware. Try again when it is idle.' } });
        return route.fulfill({ json: { items: [{ ...row, status: 'confirmed' }], total: 1, limit: 8, offset: 0 } });
    });
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('button', { name: 'Confirmed animals', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Confirmed animals', exact: true }).click();
    await page.getByRole('button', { name: 'Suggest species', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Bird inference needs the hardware');
    await expect(page.getByRole('button', { name: 'Confirm identification', exact: true })).toHaveCount(0);
});

test('tracked crop outline stays on the photographed pixels with letterboxing', async ({ page }) => {
    const identification = { outcome: 'suggestion', review: 'unreviewed', name: 'red fox', rank: 'species', score: 0.9, variant: '4.0.3a', devices: ['NPU'], country: 'GBR', input_kind: 'tracked_crop', box_xywh: [0.1, 0.2, 0.3, 0.4], frame_size: [640, 1000] };
    await page.route(url => url.pathname.startsWith('/api/garden'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/garden/identification') return route.fulfill({ json: modelStatus });
        if (path.endsWith('/snapshot')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="1000"><rect width="640" height="1000" fill="#28594a"/></svg>' });
        return route.fulfill({ json: { items: [{ ...row, status: 'confirmed', identification }], total: 1, limit: 8, offset: 0 } });
    });
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('button', { name: 'Confirmed animals', exact: true })).toBeEnabled();
    await page.getByRole('button', { name: 'Confirmed animals', exact: true }).click();
    await expect(page.getByText(/Tracked snapshot crop/)).toBeVisible();
    for (const width of [320, 1280]) {
        await page.setViewportSize({ width, height: 900 });
        await expect(page.locator('[data-garden-input] rect')).toBeVisible();
        const image = await page.locator('article img').boundingBox();
        const outline = await page.locator('[data-garden-input] rect').boundingBox();
        if (!image || !outline) throw new Error('Expected the photo and its input outline');
        const scale = Math.min(image.width / 640, image.height / 1000);
        // The visible 2px non-scaling stroke extends 1px beyond each crop edge.
        expect(outline.x).toBeCloseTo(image.x + (image.width - 640 * scale) / 2 + 64 * scale - 1, 1);
        expect(outline.y).toBeCloseTo(image.y + (image.height - 1000 * scale) / 2 + 200 * scale - 1, 1);
        expect(outline.width).toBeCloseTo(192 * scale + 2, 1);
        expect(outline.height).toBeCloseTo(400 * scale + 2, 1);
    }
});


test('motion proposals show their source and measured collector state on a narrow screen', async ({ page }) => {
    await page.route('**/api/garden?**', route => route.fulfill({ json: {items: [{...row, source_kind: 'motion', frigate_label: 'animal'}], total: 1, limit: 8, offset: 0} }));
    await page.route('**/api/garden/identification', route => route.fulfill({json: modelStatus}));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({status: 404}));
    await page.route('**/api/garden/motion', route => route.fulfill({json: {...motionStatus, cameras: ['patio'], installed: true, state: 'waiting', message: 'Waiting for bird inference to become idle.'}}));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByText('Candidate from retained motion footage')).toBeVisible();
    await expect(page.getByText('Frigate suggested: animal')).toHaveCount(0);
    await page.getByText('Motion collection', {exact: true}).click();
    await expect(page.getByText('Waiting for bird inference to become idle.')).toBeVisible();
    await expect(page.getByText(/One short recording every 120s/)).toBeVisible();
    await page.setViewportSize({width: 320, height: 740});
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});
