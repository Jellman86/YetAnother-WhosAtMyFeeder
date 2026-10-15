import { expect, test } from '@playwright/test';

const ids = ['a'.repeat(32), 'b'.repeat(32)];
const hashes = ['c'.repeat(64), 'd'.repeat(64)];
const source = { camera: 'patio', clip_start: 1, clip_end: 9, frame_index: 1, frame_offset: 1,
    clip_sha256: 'e'.repeat(64), detector_sha256: 'f'.repeat(64), detector_score: .8, box_xywh: [.1, .2, .3, .4] };
const captures = ids.map((id, index) => ({ id, camera: 'patio', frigate_label: 'animal',
    observed_at: `2026-10-15T12:00:0${2-index}Z`, reviewed_at: null, status: 'pending',
    snapshot_url: `/api/garden/${id}/snapshot`, source_kind: 'motion',
    motion_source: { ...source, clip_start: 1+index*10, clip_end: 9+index*10, image_sha256: hashes[index] } }));
const status = { country: null, catalogue_ready: true, busy: false, error: null,
    models: [{ variant: '4.0.3a', installed: true, size_bytes: 223998782 }] };
const answer = { capture_id: ids[0], image_sha256: hashes[0], suggestion: 'bird',
    mass: { bird: .85, mammal: .04, human: .001, blank: .1, other: .009 },
    variant: '4.0.3a', provider: 'cpu', devices: ['CPUExecutionProvider'],
    model_sha256: 'e'.repeat(64), package_sha256: 'f'.repeat(64), box_xywh: source.box_xywh, frame_size: [640, 360] };

test.beforeEach(async ({ page }) => {
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: captures, total: 2, limit: 128, offset: 0 } }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: status }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: { cameras: [], state: 'disabled', installed: false, catalogue_ready: true, busy: false, animal_confidence: .5 } }));
    await page.route('**/api/garden/*/snapshot', route => route.fulfill({ contentType: 'image/svg+xml', body: '<svg xmlns="http://www.w3.org/2000/svg" width="640" height="360"/>' }));
});

test('photo check is explicit, country independent and makes no review decision', async ({ page }) => {
    let checks = 0;
    let writes = 0;
    await page.route('**/api/garden/*/check-photo', async route => {
        checks++;
        expect(route.request().postDataJSON()).toEqual({ image_sha256: hashes[0], provider: 'cpu' });
        await route.fulfill({ json: answer });
    });
    await page.route(/\/api\/garden\/[^/]+\/(confirm|dismiss|restore)$/, route => { writes++; return route.fulfill({ json: captures[0] }); });
    await page.goto('/browser-tests/garden.html');
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
    expect(checks).toBe(0);
    await page.getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect(page.getByRole('dialog')).toBeVisible();
    await expect(page.getByRole('dialog')).toContainText('Model suggests a bird');
    await expect(page.getByRole('dialog')).toContainText('This photo only');
    expect(checks).toBe(1);
    expect(writes).toBe(0);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Next photo' }).click();
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
    await page.goto('/browser-tests/garden.html');
    await page.getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect.poll(() => requested).toBe(true);
    await page.keyboard.press('Escape');
    await page.getByRole('button', { name: 'Next photo' }).click();
    release?.();
    await expect(page.getByRole('dialog')).toHaveCount(0);
    await expect(page.getByText('Model suggests a bird')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
});

test('unavailable assessment preserves review controls and fits narrow dark screens', async ({ page }) => {
    await page.route('**/api/garden/*/check-photo', route => route.fulfill({ json: { ...answer, suggestion: 'unavailable', mass: null } }));
    await page.emulateMedia({ reducedMotion: 'reduce', colorScheme: 'dark' });
    await page.goto('/browser-tests/garden.html');
    await page.evaluate(() => document.documentElement.classList.add('dark'));
    await page.getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('Photo check unavailable');
    await expect(page.locator('[data-garden-check-input]')).toBeVisible();
    for (const [width, height] of [[375, 740], [740, 375]]) {
        await page.setViewportSize({ width, height });
        await page.evaluate(() => document.documentElement.style.fontSize = '200%');
        await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    }
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Confirm animal present' })).toBeEnabled();
    await expect(page.getByRole('button', { name: 'Dismiss capture', exact: true })).toBeEnabled();
});

test('a response for different crop evidence cannot become a displayed suggestion', async ({ page }) => {
    await page.route('**/api/garden/*/check-photo', route => route.fulfill({ json: { ...answer, box_xywh: [.2, .2, .3, .4] } }));
    await page.goto('/browser-tests/garden.html');
    await page.getByRole('button', { name: 'Check photo', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('does not match the displayed photo');
    await expect(page.getByRole('dialog')).not.toContainText('Model suggests a bird');
});
