import { expect, test, type Page } from '@playwright/test';

// The advisory photo check, from a Garden record in the Explorer. It answers for the photo on
// screen only, never saves a review decision, and cannot attach a late answer to another photo.

const ids = ['a'.repeat(32), 'b'.repeat(32)];
const hashes = ['c'.repeat(64), 'd'.repeat(64)];
const source = { camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1,
    clip_sha256: 'e'.repeat(64), detector_sha256: 'f'.repeat(64), detector_score: .8, box_xywh: [.1, .2, .3, .4] };
const captures = ids.map((id, index) => ({ id, camera: 'patio', frigate_label: 'animal',
    observed_at: `2026-10-15T12:00:0${2 - index}Z`, reviewed_at: null, status: 'pending',
    snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'motion', identification: null,
    automatic_check: null, automatic_check_overridden: false,
    motion_source: { ...source, clip_start: 1 + index * 10, clip_end: 9 + index * 10, image_sha256: hashes[index] } }));
// Photo checks need no country, only the tracked-crop model.
const status = { country: null, catalogue_ready: true, busy: false, error: null,
    models: [{ variant: '4.0.3a', installed: true, size_bytes: 223998782 }] };
const answer = { capture_id: ids[0], image_sha256: hashes[0], suggestion: 'bird',
    mass: { bird: .85, mammal: .04, human: .001, blank: .1, other: .009 },
    variant: '4.0.3a', provider: 'cpu', devices: ['CPUExecutionProvider'],
    model_sha256: 'e'.repeat(64), package_sha256: 'f'.repeat(64), box_xywh: source.box_xywh, frame_size: [640, 360] };

const record = (page: Page) => page.locator('[data-garden-capture-modal]');
const check = (page: Page) => page.locator('[role="dialog"]:not([data-garden-capture-modal])');

test.beforeEach(async ({ page }) => {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const url = new URL(route.request().url());
        const path = url.pathname;
        if (path === '/api/garden/timeline') {
            const items = url.searchParams.get('status') === 'pending' ? captures : [];
            return route.fulfill({ json: { items, total: items.length, limit: 128, offset: 0 } });
        }
        if (path === '/api/garden/identification') return route.fulfill({ json: status });
        if (path.endsWith('/snapshot')) return route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' });
        if (path === '/api/visits') return route.fulfill({ json: { total: 0, gap_seconds: 60, visits: [] } });
        if (path.endsWith('/filters')) return route.fulfill({ json: { species: [], cameras: [], camera_counts: {}, totals: { total: 0, favorites: 0, audio_matched: 0 } } });
        return route.fulfill({ json: { count: 0 } });
    });
});

async function openStack(page: Page) {
    await page.goto('/browser-tests/owner-history.html?surface=explorer&garden=1&visitors=garden&review=pending');
    await page.locator('[data-garden-card]').first().getByRole('button', { name: /^Open Garden capture/ }).click();
    await record(page).locator('[data-garden-manual-override] summary').click();
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
}

test('photo check is explicit, country independent and makes no review decision', async ({ page }) => {
    let checks = 0;
    let writes = 0;
    await page.route('**/api/garden/*/check-photo', async route => {
        checks++;
        expect(route.request().postDataJSON()).toEqual({ image_sha256: hashes[0], provider: 'cpu' });
        await route.fulfill({ json: answer });
    });
    await page.route(/\/api\/garden\/[^/]+\/(confirm|dismiss|restore)$/, route => { writes++; return route.fulfill({ json: captures[0] }); });
    await openStack(page);
    expect(checks).toBe(0);
    await record(page).getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect(check(page)).toContainText('Model suggests a bird');
    await expect(check(page)).toContainText('This photo only');
    expect(checks).toBe(1);
    expect(writes).toBe(0);
    // Escape closes the check first; the record stays open beneath it.
    await page.keyboard.press('Escape');
    await expect(check(page)).toHaveCount(0);
    await expect(record(page)).toBeVisible();
    await record(page).getByRole('button', { name: 'Next photo' }).click();
    await expect(page.getByText('Model suggests a bird')).toHaveCount(0);
    expect(checks).toBe(1);
});

test('closed late check cannot attach its result to the next stack photo', async ({ page }) => {
    let release: (() => void) | undefined;
    let requested = false;
    await page.route('**/api/garden/*/check-photo', async route => {
        requested = true;
        await new Promise<void>(resolve => { release = resolve; });
        await route.fulfill({ json: answer }).catch(() => {});
    });
    await openStack(page);
    await record(page).getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect.poll(() => requested).toBe(true);
    await page.keyboard.press('Escape');
    await record(page).getByRole('button', { name: 'Next photo' }).click();
    release?.();
    await expect(check(page)).toHaveCount(0);
    await expect(page.getByText('Model suggests a bird')).toHaveCount(0);
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
});

test('unavailable assessment preserves review controls and fits narrow dark screens', async ({ page }) => {
    await page.route('**/api/garden/*/check-photo', route => route.fulfill({ json: { ...answer, suggestion: 'unavailable', mass: null } }));
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
    await openStack(page);
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await record(page).getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect(check(page)).toContainText('Photo check unavailable');
    await expect(page.locator('[data-garden-check-input]')).toBeVisible();
    for (const [width, height] of [[375, 740], [740, 375]]) {
        await page.setViewportSize({ width, height });
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(record(page).getByRole('button', { name: 'Confirm animal manually' })).toBeEnabled();
    await expect(record(page).getByRole('button', { name: 'Dismiss capture', exact: true })).toBeEnabled();
});

test('a response for different crop evidence cannot become a displayed suggestion', async ({ page }) => {
    await page.route('**/api/garden/*/check-photo', route => route.fulfill({ json: { ...answer, box_xywh: [.2, .2, .3, .4] } }));
    await openStack(page);
    await record(page).getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect(check(page)).toContainText('does not match the displayed photo');
    await expect(check(page)).not.toContainText('Model suggests a bird');
});
