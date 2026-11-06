import { test, expect } from '@playwright/test';

// Set UI_SHOTS to a directory to keep review screenshots of the scan progress.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

test.beforeEach(async ({ page }) => {
    // A late external font swap can move the scan button between mouse-down
    // and mouse-up. Fixtures own their assets as well as their API responses.
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
});

function response(candidate: string, status: string, extras: Record<string, unknown> = {}) {
    return { event_id: 'fixture-event', candidate_id: candidate, status, available: true, unavailable_reason: null, error: null, result_count: status === 'completed' ? 0 : null, retained_previous: false, updated_at: null, ...extras };
}

test('ambiguous localization keeps previous findings without displaying a zero count', async ({ page }) => {
    await page.route('**/api/frigate/fixture-event/birds/scan**', route => route.fulfill({
        json: response('scene-1', 'failed', { error: 'ambiguous_localization', result_count: null, retained_previous: true })
    }));
    await page.goto('/browser-tests/bird-scan.html');
    await expect(page.getByText('Could not distinguish separate birds in this frame. Existing findings are kept. Try another whole frame.')).toBeVisible();
    await expect(page.getByText(/Scan complete\. Birds found/)).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Find more birds' })).toBeEnabled();
    await expect(page.locator('[data-scan-completions]')).toHaveText('0');
});
test('keyboard scan shows queued and completed zero results with a 44px action', async ({ page }) => {
    let started = false;
    let polls = 0;
    await page.route('**/api/frigate/fixture-event/birds/scan**', async route => {
        const post = route.request().method() === 'POST';
        if (post) {
            expect(route.request().postDataJSON()).toEqual({ candidate_id: 'scene-1', expected_media_version: 'old-revision', force: false });
            started = true;
        }
        const status = post ? 'queued' : started ? (++polls === 1 ? 'running' : 'completed') : 'not_scanned';
        await route.fulfill({ status: post ? 202 : 200, json: response('scene-1', status) });
    });
    await page.goto('/browser-tests/bird-scan.html');
    const button = page.getByRole('button', { name: 'Find more birds' });
    await expect(button).toBeEnabled();
    const box = await button.boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(44);
    expect(box?.width).toBeGreaterThanOrEqual(44);
    await button.focus();
    await page.keyboard.press('Enter');
    await expect(page.locator('[data-bird-scan-state]')).toHaveAttribute('data-bird-scan-state', 'queued');
    await expect(page.getByText('Finding birds in this whole frame.')).toBeVisible();
    await expect(page.getByText('Scan complete. Birds found in this frame: 0.')).toBeVisible();
    await expect(page.locator('[data-scan-completions]')).toHaveText('1');
});

test('new photograph ignores an old response and missing scene never starts work', async ({ page }) => {
    let release: (() => void) | undefined;
    const delayed = new Promise<void>(resolve => { release = resolve; });
    const requests: string[] = [];
    await page.route('**/api/frigate/fixture-event/birds/scan**', async route => {
        const candidate = new URL(route.request().url()).searchParams.get('candidate_id') ?? '';
        requests.push(candidate);
        if (candidate === 'scene-1') await delayed;
        await route.fulfill({ json: response(candidate, candidate === 'scene-1' ? 'completed' : 'not_scanned') }).catch(() => undefined);
    });
    await page.goto('/browser-tests/bird-scan.html');
    await expect.poll(() => requests).toContain('scene-1');
    await page.getByRole('button', { name: 'Next photograph' }).click();
    await expect(page.getByText('This whole frame has not been scanned for additional birds.')).toBeVisible();
    release?.();
    await expect(page.locator('[data-scan-completions]')).toHaveText('0');
    await page.getByRole('button', { name: 'No whole frame', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Find more birds' })).toBeDisabled();
    await expect(page.getByText('The whole frame for this photograph is unavailable.')).toBeVisible();
});

test('retained previous findings and unavailable detector are explained', async ({ page }) => {
    await page.route('**/api/frigate/fixture-event/birds/scan**', async route => {
        const candidate = new URL(route.request().url()).searchParams.get('candidate_id') ?? '';
        await route.fulfill({ json: response(candidate, candidate === 'scene-1' ? 'completed' : 'not_scanned', candidate === 'scene-1' ? { retained_previous: true } : { available: false, unavailable_reason: 'crop_model_unavailable' }) });
    });
    await page.goto('/browser-tests/bird-scan.html');
    await expect(page.getByText('The previous bird count and your corrections are kept.')).toBeVisible();
    await page.getByRole('button', { name: 'Next photograph' }).click();
    await expect(page.getByText('Install a crop detector to find additional birds.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Find more birds' })).toBeDisabled();
});

for (const theme of ['light', 'dark']) {
    test(`failure stays understandable at enlarged text on a small ${theme} screen`, async ({ page }) => {
        await page.setViewportSize({ width: 375, height: 667 });
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.route('**/api/frigate/fixture-event/birds/scan**', route => route.fulfill({ json: response('scene-1', 'failed', { error: 'interrupted' }) }));
        await page.goto('/browser-tests/bird-scan.html');
        await page.evaluate((mode) => {
            document.documentElement.classList.toggle('dark', mode === 'dark');
            document.documentElement.style.fontSize = '24px';
        }, theme);
        await expect(page.getByText('The scan was interrupted. You can try again.')).toBeVisible();
        await expect(page.getByRole('button', { name: 'Find more birds' })).toBeEnabled();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.setViewportSize({ width: 667, height: 375 });
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    });
}


test('binds a scan to displayed pixels and refuses an unversioned photo', async ({ page }) => {
    const posted: string[] = [];
    await page.route('**/api/frigate/fixture-event/birds/scan**', async route => {
        if (route.request().method() === 'POST') {
            const body = route.request().postDataJSON();
            posted.push(body.expected_media_version);
            await route.fulfill({ status: 409, json: { detail: 'media_changed' } });
        } else await route.fulfill({ json: response('scene-1', 'not_scanned') });
    });
    await page.goto('/browser-tests/bird-scan.html');
    await page.getByRole('button', { name: 'Find more birds' }).click();
    await expect(page.getByText('The scan request could not be confirmed. Checking its status before trying again.')).toBeVisible();
    expect(posted).toEqual(['old-revision']);
    await page.getByRole('button', { name: 'Retry', exact: true }).click();
    await expect(page.getByText('This whole frame has not been scanned for additional birds.')).toBeVisible();
    expect(posted).toEqual(['old-revision']);
    await page.getByRole('button', { name: 'Refresh photograph', exact: true }).click();
    await page.getByRole('button', { name: 'Find more birds' }).click();
    await expect.poll(() => posted).toEqual(['old-revision', 'new-revision']);
    await page.getByRole('button', { name: 'No image revision', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Find more birds' })).toBeDisabled();
    await expect(page.getByText('The whole frame for this photograph is unavailable.')).toBeVisible();
});


test('status reads carry the displayed revision and stale pixels stay unavailable', async ({ page }) => {
    await page.route('**/api/frigate/fixture-event/birds/scan**', async route => {
        expect(route.request().method()).toBe('GET');
        expect(new URL(route.request().url()).searchParams.get('expected_media_version')).toBe('old-revision');
        await route.fulfill({ json: response('scene-1', 'not_scanned', { available: false, unavailable_reason: 'media_changed' }) });
    });
    await page.goto('/browser-tests/bird-scan.html');
    await expect(page.getByText('The frame changed during the scan. Try again on the current frame.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Find more birds' })).toBeDisabled();
    await expect(page.getByText('Scan complete. Birds found in this frame: 0.')).toHaveCount(0);
});

test('a scan shows its place in the queue, each real step and the time it has taken', async ({ page }) => {
    const shots = environment.UI_SHOTS;
    const steps = [
        response('scene-1', 'queued', { queue_ahead: 2 }),
        response('scene-1', 'running', { started_at: new Date(Date.now() - 4000).toISOString(), stage: 'detecting' }),
        response('scene-1', 'running', { started_at: new Date(Date.now() - 6000).toISOString(), stage: 'naming', stage_done: 2, stage_total: 5 }),
        response('scene-1', 'running', { started_at: new Date(Date.now() - 8000).toISOString(), stage: 'counting' }),
        response('scene-1', 'completed', { result_count: 3 })
    ];
    let started = false;
    let position = 0;
    await page.route('**/api/frigate/fixture-event/birds/scan**', async route => {
        if (route.request().method() === 'POST') {
            started = true;
            return route.fulfill({ status: 202, json: steps[0] });
        }
        if (!started) return route.fulfill({ json: response('scene-1', 'not_scanned') });
        return route.fulfill({ json: steps[position] });
    });
    await page.goto('/browser-tests/bird-scan.html');
    await page.getByRole('button', { name: 'Find more birds' }).click();

    await expect(page.getByText('Waiting to scan this whole frame. 2 scans ahead.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Waiting…' })).toBeDisabled();
    if (shots) await page.locator('[data-bird-scan-control]').screenshot({ path: `${shots}/scan-queued.png` });

    position = 1;
    await expect(page.getByText('Looking for birds across the whole frame.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Scanning…' })).toBeDisabled();
    position = 2;
    await expect(page.getByText('Naming each bird found: 2 of 5.')).toBeVisible();
    const bar = page.getByRole('progressbar', { name: 'Scan progress' });
    await expect(bar).toHaveAttribute('aria-valuenow', '1.4');
    await expect(page.locator('[data-bird-scan-progress]')).toContainText(/\ds/);
    if (shots) await page.locator('[data-bird-scan-control]').screenshot({ path: `${shots}/scan-naming.png` });
    position = 3;
    await expect(page.getByText('Counting the birds and rechecking faint ones.')).toBeVisible();
    position = 4;
    await expect(page.getByText('Scan complete. Birds found in this frame: 3.')).toBeVisible();
    await expect(page.locator('[data-bird-scan-progress]')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Scan again' })).toBeEnabled();
});

const scene = `<svg xmlns="http://www.w3.org/2000/svg" width="3840" height="2160" viewBox="0 0 3840 2160">
<rect width="3840" height="2160" fill="#5b7a4a"/><rect x="1188" y="543" width="236" height="170" fill="#2f6db5"/>
<rect x="1754" y="476" width="178" height="174" fill="#2f6db5"/><rect x="1605" y="623" width="56" height="36" fill="#c9b27a"/></svg>`;
const uncounted = [
    { candidate_id: 'shared-foot', box: [1684, 573, 1802, 664], detector_confidence: 0.46, reason: 'shares_counted_pixels' },
    { candidate_id: 'seed-port', box: [1605, 623, 1661, 659], detector_confidence: 0.3, reason: 'confirmation_unavailable' }
];

for (const theme of ['light', 'dark']) {
    for (const width of [1280, 375]) {
        test(`incomplete count says at least N and lists what was not counted (${theme}, ${width}px)`, async ({ page }) => {
            await page.setViewportSize({ width, height: 900 });
            await page.route('**/fixture-scenes/**', route => route.fulfill({ contentType: 'image/svg+xml', body: scene }));
            await page.route('**/api/frigate/fixture-event/birds/scan**', route => route.fulfill({
                json: response('scene-1', 'completed', { result_count: 2, count_status: 'incomplete', unconfirmed_regions: uncounted, excluded_regions: [] })
            }));
            await page.goto('/browser-tests/bird-scan.html');
            await page.evaluate((mode) => { document.documentElement.classList.toggle('dark', mode === 'dark'); }, theme);
            await expect(page.getByText('At least 2 birds confirmed in this frame. 2 more possible birds were not counted.')).toBeVisible();
            await expect(page.getByText(/Birds found in this frame/)).toHaveCount(0);
            const summary = page.getByText('Show the 2 areas that were not counted');
            await summary.focus();
            await page.keyboard.press('Enter');
            await expect(page.getByText('Possible birds, not counted')).toBeVisible();
            await expect(page.getByText('Overlaps a confirmed bird, so it may be part of it')).toBeVisible();
            await expect(page.getByText('Not clear enough to count as a bird')).toBeVisible();
            await expect(page.locator('[data-bird-scan-region="unconfirmed"]')).toHaveCount(2);
            // The action keeps its place beside the sentence, above the list.
            const action = await page.getByRole('button', { name: 'Scan again' }).boundingBox();
            const list = await page.locator('[data-bird-scan-regions]').boundingBox();
            expect(action && list && action.y < list.y).toBe(true);
            expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
            await page.getByRole('button', { name: 'Area 1, not counted' }).focus();
            await expect(page.locator('[data-bird-count-region-preview]')).toBeVisible();
            if (environment.UI_SHOTS) await page.screenshot({ path: `${environment.UI_SHOTS}/incomplete-${theme}-${width}.png`, fullPage: true });
        });
    }
}

test('a complete confirmed count and an earlier unconfirmed count read differently', async ({ page }) => {
    await page.route('**/api/frigate/fixture-event/birds/scan**', route => {
        const candidate = new URL(route.request().url()).searchParams.get('candidate_id') ?? '';
        return route.fulfill({
            json: response(candidate, 'completed', { result_count: 3, count_status: candidate === 'scene-1' ? 'complete' : 'legacy' })
        });
    });
    await page.goto('/browser-tests/bird-scan.html');
    await expect(page.getByText('Scan complete. 3 birds confirmed in this frame.')).toBeVisible();
    await expect(page.locator('[data-bird-scan-regions]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Next photograph' }).click();
    await expect(page.getByText('Scan complete. Birds found in this frame: 3.')).toBeVisible();
});
