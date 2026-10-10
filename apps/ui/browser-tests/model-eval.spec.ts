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

// The shape a Detection Settings compatibility check writes: accuracy fields are
// zero placeholders and every latency field holds the provider's median latency.
const compatibilityRun = {
    run_id: '20261010-163945',
    finished_at: '2026-10-10T16:49:09Z',
    duration_seconds: 564,
    models: [
        {
            model_id: 'dinov2_location', active_provider: 'intel_npu', requested_provider: 'validation_sweep',
            ready: true, validated_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'], failed_providers: [],
            images_evaluated: 24, top1_accuracy: 0, top3_accuracy: 0, top5_accuracy: 0, abstention_rate: 0,
            high_confidence_unknown_rate: 0, mean_latency_ms: 120.4, p50_latency_ms: 120.4, p95_latency_ms: 120.4,
            shared_core_top1: 0, regional_top1: 0, warnings: []
        }
    ]
};
const compatibilityMatrix = {
    run_id: '20261010-163945', generated_at: '2026-10-10T16:49:09Z',
    providers: ['cpu', 'intel_npu'], devices: ['cpu', 'intel_npu'], image_count: 24,
    models: {
        dinov2_location: {
            baseline_provider: 'cpu', best_provider: 'intel_npu',
            providers: {
                cpu: { compiles: true, ok: true, baseline: true, images_evaluated: 24 },
                intel_npu: { compiles: true, ok: true, finite: true, matches_cpu: true, images_compared: 24, latency_ms: 120.4 }
            }
        }
    }
};

test('a compatibility-only run says accuracy was not measured instead of showing 0%', async ({ page }) => {
    const artifactRequests: string[] = [];
    let matrixLoaded = false;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/api/diagnostics/model-eval/**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [{ run_id: compatibilityRun.run_id, status: 'completed', model_count: 1 }] } });
        if (path.endsWith(`/runs/${compatibilityRun.run_id}`)) return route.fulfill({ json: compatibilityRun });
        if (path.endsWith('/device_matrix.json') && !matrixLoaded) {
            matrixLoaded = true;
            return route.fulfill({ json: compatibilityMatrix });
        }
        artifactRequests.push(path.split('/').pop() ?? '');
        return route.fulfill({ contentType: 'application/json', body: '{}' });
    });
    await page.goto('/browser-tests/model-eval.html');
    await expect(page.getByText('Compatibility check only', { exact: true })).toBeVisible();
    await expect(page.getByText(/did not measure accuracy/)).toBeVisible();
    const summary = page.getByRole('table').first();
    const row = summary.getByRole('row', { name: /dinov2_location/ });
    await expect(row).toContainText('Intel NPU');
    await expect(row).toContainText('120 ms');
    await expect(summary).not.toContainText('%');
    await expect(summary.getByRole('columnheader', { name: 'Median inference', exact: true })).toBeVisible();
    await expect(summary.getByRole('columnheader', { name: /P95|Mean|Top-1/ })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'runtime.json', exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'confusions.csv', exact: true })).toHaveCount(0);
    for (const artifact of ['summary.json', 'device_matrix.json']) {
        const downloadEvent = page.waitForEvent('download');
        await page.getByRole('button', { name: artifact, exact: true }).click();
        expect((await downloadEvent).suggestedFilename()).toBe(artifact);
    }
    expect(artifactRequests).toEqual(['summary.json', 'device_matrix.json']);
});

test('an accuracy run keeps a genuinely measured zero and its latency spread', async ({ page }) => {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/api/diagnostics/model-eval/**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [{ run_id: 'accuracy-1', status: 'completed' }] } });
        if (path.endsWith('/runs/accuracy-1')) {
            return route.fulfill({ json: { run_id: 'accuracy-1', models: [{
                ...compatibilityRun.models[0], requested_provider: 'auto', active_provider: 'cpu', mean_latency_ms: 80, p95_latency_ms: 140
            }] } });
        }
        return route.fulfill({ status: 404, json: { detail: 'missing' } });
    });
    await page.goto('/browser-tests/model-eval.html');
    const row = page.getByRole('table').first().getByRole('row', { name: /dinov2_location/ });
    await expect(row).toContainText('0.0%');
    await expect(row).toContainText('80 ms');
    await expect(row).toContainText('140 ms');
    await expect(page.getByText('Compatibility check only', { exact: true })).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'runtime.json', exact: true })).toBeVisible();
});

test('switching runs hides the old downloads until the selected run has loaded', async ({ page }) => {
    let releaseSummary: (() => void) | undefined;
    const summaryGate = new Promise<void>(resolve => { releaseSummary = resolve; });
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route('**/api/diagnostics/model-eval/**', async route => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [
            { run_id: 'accuracy-old', status: 'completed' },
            { run_id: compatibilityRun.run_id, status: 'completed' }
        ] } });
        if (path.endsWith('/runs/accuracy-old')) return route.fulfill({ json: { run_id: 'accuracy-old', models: [] } });
        if (path.endsWith(`/runs/${compatibilityRun.run_id}`)) {
            await summaryGate;
            return route.fulfill({ json: compatibilityRun });
        }
        return route.fulfill({ status: 404, json: { detail: 'missing' } });
    });
    await page.goto('/browser-tests/model-eval.html');
    await expect(page.getByRole('button', { name: 'runtime.json', exact: true })).toBeVisible();
    const requestStarted = page.waitForRequest(request => new URL(request.url()).pathname.endsWith(`/runs/${compatibilityRun.run_id}`));
    await page.getByRole('button', { name: new RegExp(compatibilityRun.run_id) }).click();
    await requestStarted;
    await expect(page.getByRole('button', { name: 'runtime.json', exact: true })).toHaveCount(0);
    releaseSummary?.();
    await expect(page.getByText('Compatibility check only', { exact: true })).toBeVisible();
});
