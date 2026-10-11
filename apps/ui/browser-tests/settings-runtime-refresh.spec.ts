import { test, expect, type Page } from '@playwright/test';

// The compatibility check can move classification onto a newly validated
// accelerator. The Detection page must then show the provider the workers
// actually run on, read back from the backend, without reloading the settings
// form and discarding edits the owner has not saved.
const cpuStatus = {
    loaded: true, error: null, labels_count: 1000, enabled: true,
    active_model_id: 'dinov2_location', image_execution_mode: 'subprocess',
    runtime_source: 'worker', selected_provider: 'auto',
    active_provider: 'cpu', inference_backend: 'onnxruntime',
    host_available_providers: ['cpu', 'intel_npu'], available_providers: ['cpu', 'intel_npu'],
    intel_npu_available: true,
    host_device_eligibility: { verified_providers: ['cpu'] }
};
const npuStatus = {
    ...cpuStatus,
    active_provider: 'intel_npu', inference_backend: 'openvino',
    host_device_eligibility: { verified_providers: ['cpu', 'intel_npu'] }
};
const matrix = {
    run_id: 'compat-1', generated_at: '2026-10-10T16:49:09Z',
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

async function openDetectionWithCompatibilityRun(
    page: Page,
    statusAfterRun: () => { status: number; json: unknown },
    savedProvider = 'auto'
) {
    const counters = {
        settingsReads: 0, statusReadsAfterRun: 0, runFinished: false,
        savedProvider, saves: [] as Record<string, unknown>[]
    };
    let runListReads = 0;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings' && request.method() === 'POST') {
            const body = request.postDataJSON() as Record<string, unknown>;
            counters.saves.push(body);
            if (typeof body.inference_provider === 'string') counters.savedProvider = body.inference_provider;
            return route.fulfill({ json: { status: 'updated' } });
        }
        if (path === '/api/settings') {
            counters.settingsReads++;
            return route.fulfill({ json: {
                frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
                mqtt_auth: false, classification_threshold: 0.6, inference_provider: counters.savedProvider
            } });
        }
        if (path === '/api/classifier/status') {
            // Like the backend, the status reports the saved preference as selected_provider.
            const selected = { selected_provider: counters.savedProvider };
            if (!counters.runFinished) return route.fulfill({ json: { ...cpuStatus, ...selected } });
            counters.statusReadsAfterRun++;
            const reply = statusAfterRun();
            if (reply.status !== 200) return route.fulfill({ status: reply.status, json: reply.json });
            return route.fulfill({ json: { ...(reply.json as object), ...selected } });
        }
        if (path === '/api/diagnostics/model-eval/runs' && request.method() === 'POST') {
            return route.fulfill({ json: { run_id: 'compat-1' } });
        }
        if (path === '/api/diagnostics/model-eval/runs') {
            runListReads++;
            if (runListReads === 1) {
                return route.fulfill({ json: { active: { run_id: 'compat-1', phase: 'device_sweep', started_at: '2026-10-10T16:39:45Z', progress: { done: 1, total: 2, label: 'dinov2_location' } }, runs: [] } });
            }
            counters.runFinished = true;
            return route.fulfill({ json: { active: null, runs: [{ run_id: 'compat-1', status: 'completed' }] } });
        }
        if (path.endsWith('/compat-1/device_matrix.json')) return route.fulfill({ json: matrix });
        if (path === '/api/models/installed' || path === '/api/models/available') return route.fulfill({ json: [] });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await page.getByRole('link', { name: 'Detection', exact: true }).click();
    return counters;
}

function runtimeCell(page: Page) {
    return page.getByRole('status').filter({ hasText: 'Runtime' }).first();
}

test('the live runtime is re-read after a compatibility check without losing unsaved edits', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }));
    const slider = page.locator('#confidence-threshold-slider');
    await expect(slider).toHaveValue('0.6');
    await slider.fill('0.75');
    await expect(runtimeCell(page)).toContainText('CPU (ONNX Runtime)');
    const settingsReadsBeforeRun = counters.settingsReads;

    await page.getByRole('button', { name: 'Run compatibility check', exact: true }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('All devices match the CPU baseline.', { timeout: 15_000 });
    await expect.poll(() => counters.statusReadsAfterRun).toBeGreaterThan(0);
    await expect(runtimeCell(page)).toContainText('Intel NPU (OpenVINO)');
    await expect(runtimeCell(page)).not.toContainText('CPU (ONNX Runtime)');

    await dialog.getByRole('button', { name: 'Close', exact: true }).last().click();
    await expect(slider).toHaveValue('0.75');
    expect(counters.settingsReads).toBe(settingsReadsBeforeRun);
    expect(errors).toEqual([]);
});

test('a failed runtime refresh is said in words rather than leaving the old provider unexplained', async ({ page }) => {
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 503, json: { detail: 'Classifier unavailable' } }));
    const slider = page.locator('#confidence-threshold-slider');
    await slider.fill('0.75');
    await page.getByRole('button', { name: 'Run compatibility check', exact: true }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('All devices match the CPU baseline.', { timeout: 15_000 });
    await expect.poll(() => counters.statusReadsAfterRun).toBeGreaterThan(0);
    await dialog.getByRole('button', { name: 'Close', exact: true }).last().click();
    await expect(page.getByRole('alert').filter({ hasText: 'could not read the runtime' })).toBeVisible();
    await expect(runtimeCell(page)).not.toContainText('Intel NPU');
    await expect(slider).toHaveValue('0.75');
});

test('a recommendation does not replace the provider reported by the worker', async ({ page }) => {
    await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: cpuStatus }));
    await page.getByRole('button', { name: 'Run compatibility check', exact: true }).click();
    const dialog = page.getByRole('dialog');
    await expect(dialog).toContainText('All devices match the CPU baseline.', { timeout: 15_000 });
    await dialog.getByRole('button', { name: 'Close', exact: true }).last().click();
    await expect(runtimeCell(page)).toContainText('CPU (ONNX Runtime)');
    await expect(runtimeCell(page)).not.toContainText('Intel NPU');
});

test('refreshing Models reads the runtime without reloading unsaved settings', async ({ page }) => {
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }));
    const slider = page.locator('#confidence-threshold-slider');
    await slider.fill('0.75');
    const settingsReads = counters.settingsReads;
    counters.runFinished = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).last().click();
    await expect(runtimeCell(page)).toContainText('Intel NPU (OpenVINO)', { timeout: 3_000 });
    await expect(slider).toHaveValue('0.75');
    expect(counters.settingsReads).toBe(settingsReads);
});

test('a runtime change after returning to Detection refreshes without another check', async ({ page }) => {
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }));
    const slider = page.locator('#confidence-threshold-slider');
    await slider.fill('0.75');
    await page.getByRole('link', { name: 'Connection', exact: true }).click();
    await page.getByRole('link', { name: 'Detection', exact: true }).click();
    await expect(runtimeCell(page)).toContainText('CPU (ONNX Runtime)');
    const settingsReads = counters.settingsReads;
    counters.runFinished = true;
    await expect(runtimeCell(page)).toContainText('Intel NPU (OpenVINO)', { timeout: 9_000 });
    await expect(slider).toHaveValue('0.75');
    expect(counters.settingsReads).toBe(settingsReads);
});

// Activating a model saves that model's recommended provider on the server.
// The open form must adopt it unless the owner has already picked another one,
// or the next unrelated save writes the old provider back.
async function refreshRuntimeFromModels(
    page: Page,
    counters: { runFinished: boolean; savedProvider: string },
    serverProvider: string
) {
    counters.savedProvider = serverProvider;
    counters.runFinished = true;
    await page.getByRole('button', { name: 'Refresh', exact: true }).last().click();
    await expect(runtimeCell(page)).toContainText('Intel NPU (OpenVINO)', { timeout: 3_000 });
}

async function applySettings(page: Page, counters: { saves: Record<string, unknown>[] }) {
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => counters.saves.length).toBe(1);
    return counters.saves[0];
}

test('a provider saved on the server replaces the loaded one in the form and in the next save', async ({ page }) => {
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }), 'cpu');
    const provider = page.locator('#inference-provider');
    const slider = page.locator('#confidence-threshold-slider');
    await expect(provider).toHaveValue('cpu');
    await slider.fill('0.75');
    const settingsReads = counters.settingsReads;

    await refreshRuntimeFromModels(page, counters, 'intel_npu');
    await expect(provider).toHaveValue('intel_npu');
    await expect(slider).toHaveValue('0.75');
    expect(counters.settingsReads).toBe(settingsReads);

    const saved = await applySettings(page, counters);
    expect(saved.inference_provider).toBe('intel_npu');
    expect(saved.classification_threshold).toBe(0.75);
});

for (const { loaded, chosen } of [{ loaded: 'cpu', chosen: 'auto' }, { loaded: 'auto', chosen: 'cpu' }]) {
    test(`an unsaved ${chosen} choice survives a server provider change from ${loaded}`, async ({ page }) => {
        const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }), loaded);
        const provider = page.locator('#inference-provider');
        await expect(provider).toHaveValue(loaded);
        await provider.selectOption(chosen);

        await refreshRuntimeFromModels(page, counters, 'intel_npu');
        await expect(provider).toHaveValue(chosen);

        const saved = await applySettings(page, counters);
        expect(saved.inference_provider).toBe(chosen);
    });
}

// A legacy stored value is left out of saves while the form shows its Auto
// fallback. Once the server reports a real provider, that becomes the saved
// baseline, so choosing Auto afterwards is an explicit change that is sent.
test('Auto chosen after a legacy provider was replaced on the server is saved', async ({ page }) => {
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }), 'rocm');
    const provider = page.locator('#inference-provider');
    await expect(provider).toHaveValue('auto');

    await refreshRuntimeFromModels(page, counters, 'intel_npu');
    await expect(provider).toHaveValue('intel_npu');
    await provider.selectOption('auto');

    const saved = await applySettings(page, counters);
    expect(saved.inference_provider).toBe('auto');
});

test('an Auto preference stays Auto while the worker runs on the NPU', async ({ page }) => {
    const counters = await openDetectionWithCompatibilityRun(page, () => ({ status: 200, json: npuStatus }), 'auto');
    const provider = page.locator('#inference-provider');
    const slider = page.locator('#confidence-threshold-slider');
    await slider.fill('0.75');

    await refreshRuntimeFromModels(page, counters, 'auto');
    await expect(provider).toHaveValue('auto');

    const saved = await applySettings(page, counters);
    expect(saved.inference_provider).toBe('auto');
    expect(saved.classification_threshold).toBe(0.75);
});
