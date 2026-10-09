import { test, expect } from '@playwright/test';

test('model evaluation artifacts download with the signed-in session and show failures in place', async ({ page }) => {
    const artifactRequests: string[] = [];
    let denied = false;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/api/diagnostics/model-eval/**', async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        expect(request.headers().authorization).toBe('Bearer fixture-owner-session');
        expect(request.url()).not.toContain('fixture-owner-session');
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [{ run_id: 'run-1', status: 'completed' }] } });
        if (path.endsWith('/runs/run-1')) return route.fulfill({ json: { run_id: 'run-1', models: [] } });
        if (path.endsWith('/device_matrix.json')) return route.fulfill({ status: 404, json: { detail: 'No device sweep' } });
        artifactRequests.push(path.split('/').pop() ?? '');
        if (denied) return route.fulfill({ status: 403, json: { detail: 'Owner privileges required for this operation' } });
        return route.fulfill({ contentType: path.endsWith('.csv') ? 'text/csv' : 'application/json', body: path.endsWith('.csv') ? 'expected,predicted\nblue tit,blue tit\n' : '{"run_id":"run-1"}' });
    });
    await page.goto('/browser-tests/model-eval.html');
    for (const artifact of ['summary.json', 'runtime.json', 'confusions.csv']) {
        const button = page.getByRole('button', { name: artifact, exact: true });
        await expect(button).toBeEnabled();
        const downloadEvent = page.waitForEvent('download');
        await button.focus();
        await page.keyboard.press('Enter');
        const download = await downloadEvent;
        expect(download.suggestedFilename()).toBe(artifact);
        expect(await download.failure()).toBeNull();
    }
    expect(artifactRequests).toEqual(['summary.json', 'runtime.json', 'confusions.csv']);
    denied = true;
    await page.getByRole('button', { name: 'summary.json', exact: true }).click();
    await expect(page.getByRole('alert')).toHaveText('Owner privileges required for this operation');
    await expect(page.getByRole('button', { name: 'summary.json', exact: true })).toBeEnabled();
});
