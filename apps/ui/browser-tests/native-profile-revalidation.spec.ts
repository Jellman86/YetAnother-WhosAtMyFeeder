import { test, expect } from '@playwright/test';

const fingerprint = 'a'.repeat(64);
const profile = { fingerprint, model_id: 'bird', provider: 'intel_gpu', blocked: true, eligible: true, reason: null };

test('owner cancels an uploading check and a late upload cannot display success', async ({ page }) => {
    let attempt: Record<string, unknown> = { state: 'idle', message: 'No check yet' };
    let releaseUpload: (() => void) | undefined;
    const uploadWait = new Promise<void>(resolve => { releaseUpload = resolve; });
    let inputs = 0;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/quarantine/revalidation/prepare')) {
            const body = route.request().postDataJSON();
            attempt = { state: 'uploading', attempt_id: body.attempt_id, profile_fingerprint: fingerprint, message: 'Waiting for upload. No native work has started.' };
            return route.fulfill({ json: attempt });
        }
        if (path.endsWith('/inputs')) {
            inputs++;
            await uploadWait;
            return route.fulfill({ status: 409, json: { detail: 'This diagnostic upload is no longer current.' } });
        }
        if (path.endsWith('/cancel')) {
            attempt = { ...attempt, state: 'cancelled', message: 'Diagnostic upload cancelled. No native work was started.' };
            return route.fulfill({ json: attempt });
        }
        if (path.endsWith('/quarantine/revalidation')) return route.fulfill({ json: { profile, attempt } });
        if (path === '/api/settings') return route.fulfill({ json: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, classification_threshold: .7 } });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await page.getByRole('link', { name: 'Detection', exact: true }).click();
    const run = page.getByRole('button', { name: 'Check quarantined profile', exact: true });
    await expect(run).toBeDisabled();
    await page.getByLabel('Three different bird photos').setInputFiles([
        'browser-tests/fixtures/native-profile-one.svg',
        'browser-tests/fixtures/native-profile-two.svg',
        'browser-tests/fixtures/native-profile-three.svg'
    ]);
    await page.getByLabel('Short bird clip').setInputFiles('browser-tests/fixtures/native-profile-clip.txt');
    await page.getByLabel('I understand this runs native code').check();
    await run.click();
    await expect.poll(() => inputs).toBe(1);
    await page.getByRole('dialog').getByRole('button', { name: 'Cancel check', exact: true }).last().click();
    await expect(page.getByRole('dialog')).toContainText('No native work was started');
    releaseUpload?.();
    await expect(page.getByRole('dialog')).not.toContainText('passed and is available');
});

for (const state of ['succeeded', 'failed', 'superseded'] as const) {
    test(`restored ${state} status uses the shared diagnostic result without inventing a pass`, async ({ page }) => {
        const message = state === 'succeeded' ? 'This exact profile passed and is available in this process.' : 'The profile remains blocked. Review the incident before retrying.';
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
        await page.route(url => url.pathname.startsWith('/api/'), route => {
            const path = new URL(route.request().url()).pathname;
            if (path.endsWith('/quarantine/revalidation')) return route.fulfill({ json: {
                profile: { ...profile, blocked: state !== 'succeeded', eligible: state !== 'succeeded' },
                attempt: { state, attempt_id: 'finished', message }
            } });
            if (path === '/api/settings') return route.fulfill({ json: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, classification_threshold: .7 } });
            if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
            if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
            return route.fulfill({ json: {} });
        });
        await page.goto('/browser-tests/settings-backfill.html');
        await page.getByRole('link', { name: 'Detection', exact: true }).click();
        await page.getByRole('button', { name: 'View check status', exact: true }).click();
        await expect(page.getByRole('dialog')).toContainText(message);
        await expect(page.getByRole('dialog').getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100');
        if (state !== 'succeeded') await expect(page.getByRole('dialog')).not.toContainText('passed and is available');
    });
}
