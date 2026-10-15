import { expect, test } from '@playwright/test';

const modelStatus = { country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [{ variant: '4.0.3b', installed: true, size_bytes: 223999179 }] };

const motionStatus = { cameras: [], installed: false, catalogue_ready: true, busy: false, state: 'disabled', message: 'Motion collection is off.', interval_seconds: 10, catchup_seconds: 1800, queue_limit: 24, photo_limit: 128, photo_retention_days: 3 };

const id = 'a'.repeat(32);
const row = { id, camera: 'patio', frigate_label: 'cat', observed_at: '2026-10-11T18:00:00Z', reviewed_at: null, status: 'pending', snapshot_url: `/api/garden/${id}/snapshot` };
const motionSource = {
    camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1,
    clip_sha256: 'a'.repeat(64), image_sha256: 'b'.repeat(64), detector_sha256: 'c'.repeat(64),
    detector_score: 0.8, box_xywh: [0.1, 0.2, 0.3, 0.4]
};

for (const size of [[640, 1000], [1280, 720], [1600, 400]]) {
    test(`presence proposal aligns with the ${size.join('x')} photo before species analysis`, async ({ page }) => {
        await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [{ ...row, source_kind: 'motion', motion_source: motionSource }], total: 1, limit: 8, offset: 0 } }));
        await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
        await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
        await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: `<svg xmlns="http://www.w3.org/2000/svg" width="${size[0]}" height="${size[1]}"><rect width="100%" height="100%" fill="#28594a"/></svg>` }));
        await page.goto('/browser-tests/garden.html');
        await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
        await expect(page.getByText('Box: MegaDetector Cedar candidate. Check the photo before confirming.')).toBeVisible();
        for (const width of [1280, 320]) {
            await page.setViewportSize({ width, height: 900 });
            await page.evaluate(() => document.documentElement.style.fontSize = '200%');
            const rect = page.locator('[data-garden-presence] rect').last();
            await expect(rect).toBeVisible();
            // Measure together: a late font load can move the article between
            // two independent browser calls without moving its box relative to the photo.
            const { image, outline } = await page.locator('article').evaluate(article => {
                const photo = article.querySelector('img');
                const box = article.querySelector('[data-garden-presence] rect:last-child');
                if (!photo || !box) throw new Error('Expected a decoded photo and detector proposal');
                return { image: photo.getBoundingClientRect().toJSON(), outline: box.getBoundingClientRect().toJSON() };
            });
            const scale = Math.min(image.width / size[0], image.height / size[1]);
            // DOM rect geometry excludes the outline's non-scaling paint stroke.
            expect(outline.x).toBeCloseTo(image.x + (image.width - size[0] * scale) / 2 + size[0] * 0.1 * scale, 1);
            expect(outline.y).toBeCloseTo(image.y + (image.height - size[1] * scale) / 2 + size[1] * 0.2 * scale, 1);
            expect(outline.width).toBeCloseTo(size[0] * 0.3 * scale, 1);
            expect(outline.height).toBeCloseTo(size[1] * 0.4 * scale, 1);
            await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        }
    });
}

test('failed motion photo hides its box and blocks presence confirmation', async ({ page }) => {
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [{ ...row, source_kind: 'motion', motion_source: motionSource }], total: 1, limit: 8, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ status: 404 }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByText('Snapshot unavailable')).toBeVisible();
    await expect(page.locator('[data-garden-presence]')).toHaveCount(0);
    await expect(page.getByText('Box: MegaDetector Cedar candidate. Check the photo before confirming.')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeDisabled();
});

for (const sourceKind of ['motion', 'frigate_event']) {
    for (const photoAvailable of [true, false]) {
        test(`dismissed ${sourceKind} photo ${photoAvailable ? 'can return to review' : 'explains why restoration is unavailable'}`, async ({ page }) => {
            let status = 'dismissed';
            let writes = 0;
            await page.route('**/api/garden?**', route => {
                const selected = new URL(route.request().url()).searchParams.get('status');
                const items = selected === status ? [{ ...row, status, source_kind: sourceKind, snapshot_url: photoAvailable ? row.snapshot_url : null }] : [];
                return route.fulfill({ json: { items, total: items.length, limit: 8, offset: 0 } });
            });
            await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
            await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
            await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' }));
            await page.route('**/api/garden/*/restore', route => {
                writes++;
                status = 'pending';
                return route.fulfill({ json: { ...row, source_kind: sourceKind, status } });
            });
            await page.goto('/browser-tests/garden.html');
            await page.getByRole('button', { name: 'Dismissed', exact: true }).click();
            const restore = page.getByRole('button', { name: 'Return to review' });
            if (photoAvailable) {
                await expect(restore).toBeEnabled();
                await restore.click();
                await expect(page.locator('[data-toast-container]')).toContainText('Photo returned to review.');
                await page.getByRole('button', { name: 'Needs review', exact: true }).click();
                await expect(page.getByText(sourceKind === 'motion' ? 'Candidate from retained motion footage' : 'Frigate suggested: cat')).toBeVisible();
                expect(writes).toBe(1);
            } else {
                await expect(restore).toBeDisabled();
                await expect(page.getByText('Photo unavailable. It cannot return to review.')).toBeVisible();
                expect(writes).toBe(0);
            }
            await page.setViewportSize({ width: 320, height: 740 });
            await page.evaluate(() => document.documentElement.style.fontSize = '200%');
            await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        });
    }
}

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
        await expect(page.locator('[data-garden-input] rect').last()).toBeVisible();
        const image = await page.locator('article img').boundingBox();
        const outline = await page.locator('[data-garden-input] rect').last().boundingBox();
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
    await expect(page.getByText(/At least 10s between scans/)).toBeVisible();
    await page.setViewportSize({width: 320, height: 740});
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('motion panel explains bounded catch-up and time of the last camera queue check', async ({ page }) => {
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [], total: 0, limit: 8, offset: 0 } }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: {
        ...motionStatus, interval_seconds: 10, catchup_seconds: 1800, queue_limit: 24,
        queued_windows: 24, queue_camera: 'patio', queue_checked_at: '2026-10-13T18:00:00Z'
    } }));
    await page.goto('/browser-tests/garden.html');
    await page.locator('[data-garden-motion] summary').click();
    await expect(page.getByText('CPU only · At least 10s between scans · Up to 128 photos · 3-day photo retention')).toBeVisible();
    await expect(page.getByText('Up to 24 short windows queued per camera from the last 30 minutes. Birds and camera pressure pause collection; brief visits can be missed.')).toBeVisible();
    await expect(page.getByText(/patio: 24 windows waiting when checked at/)).toBeVisible();
    await page.setViewportSize({ width: 320, height: 900 });
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('feeder box extent changes keep photos together with their original boxes', async ({ page }) => {
    const boxes = [
        [0.7787210464, 0.6029235840, 0.0294397354, 0.0996236165],
        [0.7807638645, 0.6024082184, 0.0539882183, 0.0722991943],
        [0.7797590256, 0.6019916534, 0.0315879822, 0.1271631241],
        [0.7814696312, 0.6021912893, 0.0293195724, 0.0882186254]
    ];
    const captures = boxes.map((box, index) => ({ ...row, id: String(index),
        snapshot_url: `/api/garden/${index}/snapshot`, source_kind: 'motion',
        motion_source: { ...motionSource, box_xywh: box } }));
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: captures, total: 4, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
    await page.goto('/browser-tests/garden.html');
    await expect(page.locator('article')).toHaveCount(1);
    await expect(page.getByText('Photos 1–4 of 4 · 1 review card', { exact: true })).toBeVisible();
    for (let index = 0; index < captures.length; index++) {
        await expect(page.locator('article img')).toHaveAttribute('src', `/api/garden/${index}/snapshot`);
        const outline = page.locator('[data-garden-presence] rect').last();
        await expect(outline).toHaveAttribute('width', String(boxes[index][2] * 1280));
        await expect(page.getByText(`Photo ${index + 1} of 4`, { exact: true })).toBeVisible();
        if (index + 1 < captures.length) await page.getByRole('button', { name: 'Next photo', exact: true }).click();
    }
});

test('109 repeated proposals become two position groups with exact photo review and bounded dismissal', async ({ page }) => {
    const originals = Array.from({ length: 109 }, (_, index) => ({ ...row, id: index.toString(16).padStart(32, '0'),
        snapshot_url: `/api/garden/${index.toString(16).padStart(32, '0')}/snapshot`, source_kind: 'motion',
        observed_at: new Date(Date.UTC(2026, 9, 14, 1, 0, index)).toISOString(),
        motion_source: { ...motionSource, box_xywh: index === 108 ? [0.7, 0.1, 0.2, 0.2] : motionSource.box_xywh } }));
    let pending = [...originals];
    const writes: { ids: string[]; action: string }[] = [];
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: pending, total: pending.length, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: { ...motionStatus, last_outcome: 'storage_full' } }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
    await page.route('**/api/garden/review-batch', route => {
        const body = route.request().postDataJSON() as { ids: string[]; action: string };
        writes.push(body);
        pending = body.action === 'dismiss' ? pending.filter(item => !body.ids.includes(item.id)) : [...originals];
        return route.fulfill({ json: { updated_ids: body.ids, skipped_count: 0 } });
    });
    await page.goto('/browser-tests/garden.html');
    await expect(page.locator('article')).toHaveCount(2);
    await expect(page.getByText('Photos 1–109 of 109 · 2 review cards', { exact: true })).toBeVisible();
    const group = page.locator('article').first();
    await expect(group.getByText('108 photos around the same position')).toBeVisible();
    await expect(group.getByText('Position does not identify an animal. This group can contain different visitors.')).toBeVisible();
    await group.getByRole('button', { name: 'Next photo', exact: true }).click();
    await expect(group.locator('img')).toHaveAttribute('src', /00000000000000000000000000000001\/snapshot/);
    await expect(group.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
    await page.setViewportSize({ width: 320, height: 900 });
    await page.evaluate(() => document.documentElement.style.fontSize = '200%');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await expect(group.getByRole('button', { name: 'Dismiss remaining 108 photos', exact: true })).toBeVisible();
    await group.getByRole('button', { name: 'Dismiss remaining 108 photos', exact: true }).click();
    expect(writes[0]).toEqual({ action: 'dismiss', ids: originals.slice(0, 108).map(item => item.id) });
    await expect(page.locator('article')).toHaveCount(1);
    await expect(page.getByText('Photos 1–1 of 1 · 1 review card', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Undo group dismissal', exact: true }).click();
    await expect(page.locator('article')).toHaveCount(2);
    expect(writes[1]).toEqual({ action: 'restore', ids: writes[0].ids });
});

for (const concurrentReview of [false, true]) {
    for (const keptIndex of [0, 1]) {
        test(`scan an 80-photo stack, keep photo ${keptIndex + 1} and dismiss the rest${concurrentReview ? ' with another owner review and a new capture' : ''}`, async ({ page }) => {
            const captures = Array.from({ length: 81 }, (_, index) => ({ ...row,
                id: index.toString(16).padStart(32, '0'),
                snapshot_url: `/api/garden/${index.toString(16).padStart(32, '0')}/snapshot`,
                source_kind: 'motion', motion_source: { ...motionSource, box_xywh: index === 80 ? [0.7, 0.1, 0.2, 0.2] : motionSource.box_xywh }
            }));
            const states = new Map(captures.map(item => [item.id, 'pending']));
            const writes: { ids: string[]; action: string }[] = [];
            const animalId = captures[keptIndex].id;
            const concurrentId = captures[keptIndex + 1].id;
            await page.route('**/api/garden?**', route => {
                const status = new URL(route.request().url()).searchParams.get('status');
                const items = captures.filter(item => states.get(item.id) === status).map(item => ({ ...item, status }));
                return route.fulfill({ json: { items, total: items.length, limit: 128, offset: 0 } });
            });
            await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
            await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
            await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
            await page.route('**/api/garden/*/confirm', route => {
                const id = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
                states.set(id, 'confirmed');
                return route.fulfill({ json: { ...captures.find(item => item.id === id), status: 'confirmed' } });
            });
            await page.route('**/api/garden/review-batch', route => {
                const body = route.request().postDataJSON() as { ids: string[]; action: string };
                writes.push(body);
                if (concurrentReview && body.action === 'dismiss') {
                    states.set(concurrentId, 'confirmed');
                    const id = 'f'.repeat(32);
                    captures.push({ ...captures[0], id, snapshot_url: `/api/garden/${id}/snapshot` });
                    states.set(id, 'pending');
                }
                const updated = body.ids.filter(id => states.get(id) === (body.action === 'dismiss' ? 'pending' : 'dismissed'));
                for (const id of updated) states.set(id, body.action === 'dismiss' ? 'dismissed' : 'pending');
                return route.fulfill({ json: { updated_ids: updated, skipped_count: body.ids.length - updated.length } });
            });
            await page.goto('/browser-tests/garden.html');
            const stack = page.locator('article').first();
            await expect(stack.getByRole('button', { name: 'Dismiss remaining 80 photos', exact: true })).toBeVisible();
            if (keptIndex > 0) await stack.getByRole('button', { name: 'Next photo', exact: true }).click();
            await expect(stack.locator('img')).toHaveAttribute('src', new RegExp(`${animalId}/snapshot$`));
            await stack.getByRole('button', { name: 'Confirm animal present', exact: true }).click();
            await expect(stack.locator('img')).toHaveAttribute('src', new RegExp(`${captures[keptIndex + 1].id}/snapshot$`));
            await expect(stack.getByText(`Photo ${keptIndex + 1} of 79`, { exact: true })).toBeVisible();
            await stack.getByRole('button', { name: 'Dismiss remaining 79 photos', exact: true }).click();
            await expect(page.locator('[data-toast-container]')).toContainText(`${concurrentReview ? 78 : 79} photos dismissed.`);
            expect(writes[0]).toEqual({ action: 'dismiss', ids: captures.slice(0, 80).filter(item => item.id !== animalId).map(item => item.id) });
            expect(states.get(animalId)).toBe('confirmed');
            expect(states.get(captures[80].id)).toBe('pending');
            if (concurrentReview) {
                expect(states.get(concurrentId)).toBe('confirmed');
                expect(states.get('f'.repeat(32))).toBe('pending');
                await expect(page.locator('[data-toast-container]')).toContainText('1 photos were unchanged');
            }
            await page.getByRole('button', { name: 'Undo group dismissal', exact: true }).click();
            await expect(page.locator('[data-toast-container]')).toContainText(`${concurrentReview ? 78 : 79} photos returned to review.`);
            expect(writes[1].ids).not.toContain(animalId);
            if (concurrentReview) expect(writes[1].ids).not.toContain(concurrentId);
            expect(states.get(animalId)).toBe('confirmed');
            await page.getByRole('button', { name: 'Confirmed animals', exact: true }).click();
            await expect(page.locator('article')).toHaveCount(concurrentReview ? 2 : 1);
            await expect(page.locator(`article img[src$="/${animalId}/snapshot"]`)).toBeVisible();
        });
    }
}

test('a failed stack dismissal keeps its photos reviewable and does not offer a false Undo', async ({ page }) => {
    const captures = [row.id, 'b'.repeat(32)].map(id => ({ ...row, id, snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'motion', motion_source: motionSource }));
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: captures, total: 2, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
    await page.route('**/api/garden/review-batch', route => route.fulfill({ status: 503, json: { detail: 'Stack review temporarily unavailable.' } }));
    await page.goto('/browser-tests/garden.html');
    await page.getByRole('button', { name: 'Dismiss remaining 2 photos', exact: true }).click();
    await expect(page.locator('[data-toast-container]')).toContainText('Stack review temporarily unavailable.');
    await expect(page.locator('[data-toast-container]')).not.toContainText('photos dismissed.');
    await expect(page.getByRole('button', { name: 'Dismiss remaining 2 photos', exact: true })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Undo group dismissal', exact: true })).toHaveCount(0);
    await expect(page.getByText('2 photos around the same position', { exact: true })).toBeVisible();
});

test('animal threshold saves only the independent Garden setting and reloads measured status', async ({ page }) => {
    let confidence = 0.5;
    let saved: unknown;
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [], total: 0, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: { ...motionStatus, animal_confidence: confidence } }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/settings', route => {
        saved = route.request().postDataJSON();
        confidence = 0.6;
        return route.fulfill({ json: { status: 'success' } });
    });
    await page.goto('/browser-tests/garden.html');
    await page.getByText('Motion collection', { exact: true }).click();
    const threshold = page.getByRole('spinbutton', { name: 'Animal proposal threshold' });
    await expect(threshold).toHaveValue('0.5');
    const save = page.getByRole('button', { name: 'Save animal threshold' });
    await expect(save).toBeDisabled();
    await threshold.fill('0.6');
    await save.click();
    await expect(threshold).toHaveValue('0.6');
    await expect(save).toBeDisabled();
    expect(saved).toEqual({ garden_motion_confidence: 0.6 });
    await threshold.fill('0.2');
    await expect(save).toBeDisabled();
});

for (const action of ['confirm', 'dismiss'] as const) {
    test(`${action} visibly saves only the displayed photo while similar photos remain`, async ({ page }) => {
        const second = 'b'.repeat(32);
        const captures = [row.id, second].map(id => ({ ...row, id, snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'motion', motion_source: motionSource }));
        let pending = [...captures];
        const writes: string[] = [];
        await page.route('**/api/garden?**', route => route.fulfill({ json: { items: pending, total: pending.length, limit: 128, offset: 0 } }));
        await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
        await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
        await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
        await page.route(`**/api/garden/*/${action}`, route => {
            const reviewed = new URL(route.request().url()).pathname.split('/').at(-2) ?? '';
            writes.push(reviewed);
            pending = pending.filter(item => item.id !== reviewed);
            return route.fulfill({ json: { ...captures[1], status: action === 'confirm' ? 'confirmed' : 'dismissed' } });
        });
        await page.goto('/browser-tests/garden.html');
        await expect(page.getByText('Review this photo', { exact: true })).toBeVisible();
        await page.getByRole('button', { name: 'Next photo', exact: true }).click();
        await page.getByRole('button', { name: action === 'confirm' ? 'Confirm animal present' : 'Dismiss capture', exact: true }).click();
        await expect(page.locator('[data-toast-container]')).toContainText(action === 'confirm' ? 'Photo confirmed.' : 'Photo dismissed.');
        await expect(page.locator('[data-toast-container]')).toContainText('Other photos in this group still need review.');
        await expect(page.locator('article img')).toHaveAttribute('src', new RegExp(`${row.id}/snapshot$`));
        await expect(page.getByText('Photos 1–1 of 1 · 1 review card', { exact: true })).toBeVisible();
        expect(writes).toEqual([second]);
        await page.setViewportSize({ width: 320, height: 740 });
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
}

test('failed review stays pending and never announces success', async ({ page }) => {
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [row], total: 1, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
    await page.route('**/api/garden/*/dismiss', route => route.fulfill({ status: 503, json: { detail: 'Review temporarily unavailable.' } }));
    await page.goto('/browser-tests/garden.html');
    await page.getByRole('button', { name: 'Dismiss capture', exact: true }).click();
    await expect(page.getByRole('alert')).toContainText('Review temporarily unavailable.');
    await expect(page.locator('[data-toast-container]')).toContainText('Review temporarily unavailable.');
    await expect(page.locator('[data-toast-container]')).not.toContainText('Photo dismissed.');
    await expect(page.locator('article')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Dismiss capture', exact: true })).toBeEnabled();
});

test('confirmation in a position group applies only to the displayed original photo', async ({ page }) => {
    const second = 'b'.repeat(32);
    const captures = [row.id, second].map(id => ({ ...row, id, snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'motion', motion_source: motionSource }));
    const confirmed: string[] = [];
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: captures, total: 2, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: motionStatus }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"/>' }));
    await page.route('**/api/garden/*/confirm', route => {
        confirmed.push(new URL(route.request().url()).pathname.split('/').at(-2) ?? '');
        return route.fulfill({ json: { ...captures[1], status: 'confirmed' } });
    });
    await page.goto('/browser-tests/garden.html');
    await page.getByRole('button', { name: 'Next photo', exact: true }).click();
    await page.getByRole('button', { name: 'Confirm animal present', exact: true }).click();
    expect(confirmed).toEqual([second]);
});

for (const seconds of [5, 10]) {
    test(`motion panel displays the selected ${seconds}-second interval`, async ({ page }) => {
        await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [], total: 0, limit: 8, offset: 0 } }));
        await page.route('**/api/garden/identification', route => route.fulfill({ json: modelStatus }));
        await page.route('**/api/garden/motion', route => route.fulfill({ json: {
            ...motionStatus, cameras: ['patio'], installed: true, state: 'waiting',
            interval_seconds: seconds, queued_windows: seconds === 5 ? 23 : 0,
            queue_camera: 'patio', queue_checked_at: '2026-10-14T13:00:00Z',
            last_outcome: 'no_candidate', message: 'Recording scanned; no review photo retained.'
        } }));
        await page.goto('/browser-tests/garden.html');
        await page.locator('[data-garden-motion] > summary').click();
        await expect(page.getByText(`CPU only · At least ${seconds}s between scans · Up to 128 photos · 3-day photo retention`)).toBeVisible();
        await page.setViewportSize({ width: 320, height: 740 });
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
}
