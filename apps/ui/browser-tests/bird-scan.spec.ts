import { test, expect } from '@playwright/test';

function response(candidate: string, status: string, extras: Record<string, unknown> = {}) {
    return { event_id: 'fixture-event', candidate_id: candidate, status, available: true, unavailable_reason: null, error: null, result_count: status === 'completed' ? 0 : null, retained_previous: false, updated_at: null, ...extras };
}
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
