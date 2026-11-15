import AxeBuilder from '@axe-core/playwright';
import { test, expect, type Page, type Route } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';

const EVAL_API = '**/api/diagnostics/model-eval/**';
const RUNS = '**/api/diagnostics/model-eval/runs';

/** The component on its own: no font or model registry request leaves the machine. */
async function openFixture(page: Page): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route('**/api/models/**', (route) => route.fulfill({ json: [] }));
    await page.goto('/browser-tests/model-eval.html');
}

const downloadButton = (page: Page, label: string, file: string) =>
    page.getByRole('button', { name: `Download ${label} (${file})`, exact: true });

test('result files download with the signed-in session, and a refused download says why in place', async ({ page }) => {
    const requested: string[] = [];
    let denied = false;
    await page.route(EVAL_API, async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        expect(request.headers().authorization).toBe('Bearer fixture-owner-session');
        expect(request.url()).not.toContain('fixture-owner-session');
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [{ run_id: 'run-1', status: 'complete' }] } });
        if (path.endsWith('/runs/run-1')) {
            return route.fulfill({ json: { run_id: 'run-1', models: [], available_artifacts: ['summary.json', 'confusions.csv', 'runtime.json'] } });
        }
        requested.push(path.split('/').pop() ?? '');
        if (denied) return route.fulfill({ status: 403, json: { detail: 'Owner privileges required for this operation' } });
        return route.fulfill({ contentType: path.endsWith('.csv') ? 'text/csv' : 'application/json', body: path.endsWith('.csv') ? 'expected,predicted\nblue tit,blue tit\n' : '{"run_id":"run-1"}' });
    });
    await openFixture(page);
    for (const [label, file] of [['Summary', 'summary.json'], ['Mix-ups', 'confusions.csv'], ['Speed details', 'runtime.json']]) {
        const button = downloadButton(page, label, file);
        await expect(button).toBeEnabled();
        // The visible words are the plain label; the file name is in the accessible name only.
        await expect(button).toHaveText(label);
        const downloadEvent = page.waitForEvent('download');
        await button.focus();
        await page.keyboard.press('Enter');
        const download = await downloadEvent;
        expect(download.suggestedFilename()).toBe(file);
        expect(await download.failure()).toBeNull();
    }
    expect(requested).toEqual(['summary.json', 'confusions.csv', 'runtime.json']);
    // A file the evaluation did not write is not offered, and its absence is not probed for.
    await expect(page.getByRole('button', { name: /device_matrix|results\.jsonl/ })).toHaveCount(0);

    denied = true;
    await downloadButton(page, 'Summary', 'summary.json').click();
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('The file was not downloaded.');
    await expect(alert).toContainText('Your sign-in has expired or is not the owner\'s. Sign in again, then retry.');
    await expect(downloadButton(page, 'Summary', 'summary.json')).toBeEnabled();
});

// The shape a compatibility check from Settings writes: accuracy fields are
// zero placeholders and every latency field holds the provider's median latency.
const compatibilityRun = {
    run_id: '20261010-163945',
    finished_at: '2026-10-10T16:49:09Z',
    duration_seconds: 564,
    available_artifacts: ['summary.json', 'device_matrix.json'],
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
    providers: ['cpu', 'intel_gpu', 'intel_npu'], devices: ['cpu', 'intel_gpu', 'intel_npu'], image_count: 24,
    models: {
        dinov2_location: {
            baseline_provider: 'cpu', best_provider: 'intel_npu',
            providers: {
                cpu: { compiles: true, ok: true, baseline: true, images_evaluated: 24 },
                intel_gpu: { compiles: true, finite: true, matches_cpu: false, images_compared: 24, top1_match_rate: 0.75 },
                intel_npu: { compiles: true, ok: true, finite: true, matches_cpu: true, images_compared: 24, latency_ms: 120.4 }
            }
        }
    }
};

test('a provider check says accuracy was not measured instead of showing 0%, and writes each result in words', async ({ page }) => {
    const requested: string[] = [];
    await page.route(EVAL_API, async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [{ run_id: compatibilityRun.run_id, status: 'complete', model_count: 1 }] } });
        if (path.endsWith(`/runs/${compatibilityRun.run_id}`)) return route.fulfill({ json: compatibilityRun });
        requested.push(path.split('/').pop() ?? '');
        if (path.endsWith('/device_matrix.json')) return route.fulfill({ json: compatibilityMatrix });
        return route.fulfill({ contentType: 'application/json', body: '{}' });
    });
    await openFixture(page);
    await expect(page.getByText('Provider check only', { exact: true })).toBeVisible();
    await expect(page.getByText(/did not measure accuracy/)).toBeVisible();
    const summary = page.getByRole('table').first();
    const row = summary.getByRole('row', { name: /dinov2_location/ });
    await expect(row).toContainText('Intel NPU');
    await expect(row).toContainText('120 ms');
    await expect(summary).not.toContainText('%');
    await expect(summary.getByRole('columnheader', { name: 'Typical time per photo', exact: true })).toBeVisible();
    await expect(summary.getByRole('columnheader', { name: /Slow photos|Average time|First guess/ })).toHaveCount(0);

    const checks = page.getByRole('region', { name: 'Provider checks' }).getByRole('table');
    const checkRow = checks.getByRole('row', { name: /dinov2_location/ });
    await expect(checkRow.getByRole('cell').nth(0)).toHaveText('Reference, 24 photos');
    await expect(checkRow.getByRole('cell').nth(1)).toHaveText('Differs: same on 18 of 24 photos');
    await expect(checkRow.getByRole('cell').nth(2)).toHaveText('Same on all 24 photos');
    await expect(checks.getByRole('columnheader', { name: 'Intel NPU (OpenVINO)', exact: true })).toBeVisible();

    await expect(page.getByRole('button', { name: /runtime\.json|confusions\.csv/ })).toHaveCount(0);
    for (const [label, file] of [['Summary', 'summary.json'], ['Provider checks', 'device_matrix.json']]) {
        const downloadEvent = page.waitForEvent('download');
        await downloadButton(page, label, file).click();
        expect((await downloadEvent).suggestedFilename()).toBe(file);
    }
    // The matrix is read once for the page and once for the download; nothing else is asked for.
    expect(requested).toEqual(['device_matrix.json', 'summary.json', 'device_matrix.json']);
});

const accuracyModel = {
    ...compatibilityRun.models[0], requested_provider: 'auto', active_provider: 'cpu', mean_latency_ms: 80, p95_latency_ms: 140
};

test('an accuracy run keeps a genuinely measured zero, its latency spread and a warning in plain words', async ({ page }) => {
    await page.route(EVAL_API, async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [{ run_id: 'accuracy-1', status: 'complete' }] } });
        if (path.endsWith('/runs/accuracy-1')) {
            return route.fulfill({ json: { run_id: 'accuracy-1', available_artifacts: ['summary.json', 'runtime.json'], models: [{
                ...accuracyModel,
                startup_benchmark_ms: 10,
                warnings: [
                    { code: 'latency_drift_high', message: 'measured mean 80 ms is 8.0× the startup benchmark (10 ms)', severity: 'critical' },
                    { code: 'not_known_here', message: 'words from the server', severity: 'info' }
                ]
            }] } });
        }
        return route.fulfill({ status: 404, json: { detail: 'missing' } });
    });
    await openFixture(page);
    const table = page.getByRole('table').first();
    const row = table.getByRole('row', { name: /dinov2_location/ }).first();
    await expect(row).toContainText('0.0%');
    await expect(row).toContainText('80 ms');
    await expect(row).toContainText('140 ms');
    await expect(row).toContainText('CPU (ONNX Runtime)');
    await expect(table.getByRole('columnheader', { name: 'First guess right', exact: true })).toBeVisible();
    await expect(table).toContainText('Much slower than when it was loaded: 80 ms a photo against 10 ms.');
    await expect(table).toContainText('Set the inference provider to CPU in Settings → Models and evaluate again.');
    await expect(table).not.toContainText('latency_drift_high');
    await expect(table).not.toContainText('startup benchmark');
    // A warning this page does not know gets its own sentence; the server's words are never the copy.
    await expect(table).toContainText('Flagged for a reason this version of the page cannot explain. The Summary download has the detail.');
    await expect(table).not.toContainText('words from the server');
    await expect(page.getByText('Provider check only', { exact: true })).toHaveCount(0);
    await expect(downloadButton(page, 'Speed details', 'runtime.json')).toBeVisible();
});

test('choosing another evaluation hides the old downloads until the chosen one has loaded', async ({ page }) => {
    let releaseSummary: (() => void) | undefined;
    const summaryGate = new Promise<void>((resolve) => { releaseSummary = resolve; });
    await page.route(EVAL_API, async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [
            { run_id: '20261101-090000', status: 'complete' },
            { run_id: compatibilityRun.run_id, status: 'complete' }
        ] } });
        if (path.endsWith('/runs/20261101-090000')) return route.fulfill({ json: { run_id: '20261101-090000', models: [], available_artifacts: ['summary.json', 'runtime.json'] } });
        if (path.endsWith(`/runs/${compatibilityRun.run_id}`)) {
            await summaryGate;
            return route.fulfill({ json: { ...compatibilityRun, available_artifacts: ['summary.json'] } });
        }
        return route.fulfill({ status: 404, json: { detail: 'missing' } });
    });
    await openFixture(page);
    await expect(downloadButton(page, 'Speed details', 'runtime.json')).toBeVisible();
    // An evaluation is named by when it started, read from its identifier (UTC) in the reader's zone.
    const chooser = page.getByLabel('Evaluation', { exact: true });
    await expect(chooser.locator('option')).toHaveText(['01/11/2026 09:00', '10/10/2026 17:39']);
    const requestStarted = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith(`/runs/${compatibilityRun.run_id}`));
    await chooser.selectOption(compatibilityRun.run_id);
    await requestStarted;
    await expect(downloadButton(page, 'Speed details', 'runtime.json')).toHaveCount(0);
    await expect(page.getByRole('status', { name: 'Reading the results' })).toBeVisible();
    releaseSummary?.();
    await expect(page.getByText('Provider check only', { exact: true })).toBeVisible();
});

test('a failed read says what failed and how to go on, never that there are no evaluations', async ({ page }) => {
    let failing = true;
    let releaseFirst: (() => void) | undefined;
    const firstGate = new Promise<void>((resolve) => { releaseFirst = resolve; });
    await page.route(EVAL_API, async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (failing) {
            await firstGate;
            return route.fulfill({ status: 500, body: 'Internal Server Error' });
        }
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [] } });
        return route.fulfill({ status: 404, json: { detail: 'missing' } });
    });
    await openFixture(page);
    // While the read is out, the page holds its place and claims nothing.
    await expect(page.getByRole('status', { name: 'Reading the past evaluations' })).toBeVisible();
    await expect(page.locator('[data-model-eval-empty]')).toHaveCount(0);
    releaseFirst?.();

    const alert = page.getByRole('alert');
    await expect(alert).toContainText('The past evaluations could not be read.');
    await expect(alert).toContainText('YA-WAMF hit an error while handling the request. Try again; if it keeps failing, look at the container logs.');
    await expect(page.getByText('Internal Server Error')).toHaveCount(0);
    await expect(page.locator('[data-model-eval-empty]')).toHaveCount(0);

    failing = false;
    await alert.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    await expect(page.locator('[data-model-eval-empty]')).toHaveText('No evaluation has been run yet. Start one above and its results appear here.');
});

test('a start that fails names the cause, and a running evaluation shows named progress and re-reads only itself', async ({ page }) => {
    let startStatus = 500;
    const summaryReads: Record<string, number> = {};
    let active: object | null = null;
    await page.route(EVAL_API, async (route) => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path.endsWith('/runs') && request.method() === 'POST') {
            if (startStatus === 200) {
                active = { run_id: '20261115-070000', phase: 'evaluating', started_at: '2026-11-15T07:00:00Z', progress: { done: 1, total: 4, label: 'small_birds 40/423 images' } };
                return route.fulfill({ json: { run_id: '20261115-070000' } });
            }
            return route.fulfill(startStatus === 409
                ? { status: 409, json: { detail: 'A run is already in progress' } }
                : { status: 500, body: 'Internal Server Error' });
        }
        if (path.endsWith('/runs')) {
            return route.fulfill({ json: { active, runs: [
                ...(active ? [{ run_id: '20261115-070000', status: 'in_progress' }] : []),
                { run_id: '20261101-090000', status: 'complete' }
            ] } });
        }
        const runId = path.split('/').pop() ?? '';
        summaryReads[runId] = (summaryReads[runId] ?? 0) + 1;
        if (runId === '20261115-070000') return route.fulfill({ json: { run_id: runId, models: [], in_progress: true, available_artifacts: [] } });
        return route.fulfill({ json: { run_id: runId, models: [accuracyModel], available_artifacts: ['summary.json'] } });
    });
    await openFixture(page);
    const start = page.getByRole('button', { name: 'Start evaluation', exact: true });
    await start.click();
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('The evaluation did not start.');
    await expect(alert).toContainText('look at the container logs');
    await expect(page.getByText('Internal Server Error')).toHaveCount(0);

    startStatus = 409;
    await start.click();
    await expect(alert).toContainText('Another evaluation is already running. Wait for it to finish, or stop it first.');

    startStatus = 200;
    await start.click();
    await expect(page.getByRole('alert')).toHaveCount(0);
    const running = page.getByRole('button', { name: 'Evaluation running', exact: true });
    await expect(running).toBeDisabled();
    await expect(running).toHaveAccessibleDescription('One evaluation runs at a time. Stop this one to start another.');
    await expect(page.getByRole('button', { name: 'Stop evaluation', exact: true })).toBeVisible();
    const bar = page.getByRole('progressbar', { name: 'Progress of the evaluation' });
    await expect(bar).toHaveAttribute('aria-valuenow', '25');
    await expect(page.locator('[data-model-eval-progress]')).toContainText('Testing models');
    await expect(page.locator('[data-model-eval-progress]')).toContainText('1 of 4');
    // The server's internal label is not copy.
    await expect(page.locator('[data-model-eval-progress]')).not.toContainText('small_birds 40/423');
    await expect(page.locator('[data-model-eval-still-running]')).toBeVisible();
    const remove = page.getByRole('button', { name: 'Delete this evaluation', exact: true });
    await expect(remove).toBeDisabled();
    await expect(remove).toHaveAccessibleDescription('Stop it before you delete it.');

    // A finished evaluation does not change: while the page polls, it is not read again.
    await page.getByLabel('Evaluation', { exact: true }).selectOption('20261101-090000');
    await expect(page.getByRole('table').first()).toBeVisible();
    const before = summaryReads['20261101-090000'];
    await page.waitForTimeout(4_500);
    expect(summaryReads['20261101-090000']).toBe(before);
});

// ---- The page inside the real app -------------------------------------------------------------

const RUN_ID = '20261114-081500';
const fullRun = {
    run_id: RUN_ID, started_at: '2026-11-14T08:15:00+00:00', finished_at: '2026-11-14T08:31:12+00:00', duration_seconds: 972,
    test_set: { shared_core_species: 50, regional_species: 91, total_species: 141, images_per_species: 3, total_images: 423, region: 'GB-ENG', image_sources: {} },
    available_artifacts: ['summary.json', 'confusions.csv', 'runtime.json', 'results.jsonl', 'device_matrix.json'],
    skipped_models: [{ model_id: 'eva02_large_inat21', reason: 'activation_failed', detail: 'The model\'s files are missing or incomplete, so it could not be run.' }],
    models: [
        { ...accuracyModel, model_id: 'convnext_large_inat21', active_provider: 'intel_gpu', top1_accuracy: 0.9, top3_accuracy: 0.95, shared_core_top1: 0.92, regional_top1: 0.88 },
        {
            ...accuracyModel, model_id: 'small_birds', vocabulary_known: true, panel_species: 141, species_outside_vocabulary: 26,
            top1_accuracy_in_vocabulary: 0.83, top3_accuracy_in_vocabulary: 0.9, shared_core_top1_in_vocabulary: 0.86, regional_top1_in_vocabulary: 0.81,
            mean_latency_ms: 2410, p95_latency_ms: 3980, startup_benchmark_ms: 310,
            warnings: [
                { code: 'latency_drift_high', message: 'x', severity: 'critical' },
                { code: 'provider_fallback_active', message: 'x', severity: 'warning' },
                { code: 'partial_vocabulary', message: 'x', severity: 'info' }
            ]
        }
    ]
};
const fullMatrix = {
    ...compatibilityMatrix, run_id: RUN_ID, image_flavor: 'intel',
    models: {
        convnext_large_inat21: compatibilityMatrix.models.dinov2_location,
        small_birds: { baseline_provider: 'cpu', providers: {
            cpu: { compiles: true, baseline: true, images_evaluated: 24 },
            intel_gpu: { compiles: false },
            intel_npu: { compiles: true, finite: false }
        } }
    },
    crop_detectors: { bird_crop_detector: { comparison_kind: 'crop_box', baseline_provider: 'cpu', providers: {
        cpu: { compiles: true, baseline: true, images_evaluated: 27 },
        intel_gpu: { compiles: true, matches_cpu: true, images_compared: 27 }
    } } }
};
const REGISTRY = [
    { id: 'convnext_large_inat21', name: 'ConvNeXt Large (High Accuracy)', file_size_mb: 760 },
    { id: 'small_birds', name: 'Small Birds', file_size_mb: 12.4 },
    { id: 'eva02_large_inat21', name: 'EVA-02 Large (Elite Accuracy)', file_size_mb: 1250 },
    { id: 'bird_crop_detector', name: 'Bird Crop Detector', file_size_mb: 19.3, artifact_kind: 'crop_detector' }
];
const INSTALLED = [{ id: 'convnext_large_inat21', ready: true }, { id: 'small_birds', ready: true }];

const withEvaluation = {
    '/api/diagnostics/model-eval/runs': { active: null, runs: [
        { run_id: RUN_ID, status: 'complete', started_at: fullRun.started_at },
        { run_id: '20261110-070000', status: 'complete', error_code: 'no_test_photos' }
    ] },
    [`/api/diagnostics/model-eval/runs/${RUN_ID}`]: fullRun,
    [`/api/diagnostics/model-eval/runs/${RUN_ID}/device_matrix.json`]: fullMatrix,
    '/api/models/available': REGISTRY,
    '/api/models/installed': INSTALLED
};

async function openEvaluation(page: Page, theme: Theme = 'light', overrides: Record<string, unknown> = withEvaluation): Promise<void> {
    await replayFeeder(page, theme, overrides);
    await page.goto('/diagnostics/model-eval');
    await expect(page.getByRole('heading', { level: 1, name: 'Model evaluation', exact: true })).toBeVisible({ timeout: 15_000 });
    await settled(page);
}

for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    for (const theme of ['light', 'dark'] as const) {
        test(`the page with results and its options open has no axe finding at ${viewport.width} in ${theme}`, async ({ page }) => {
            await page.setViewportSize(viewport);
            await openEvaluation(page, theme);
            await page.getByRole('button', { name: 'Show evaluation options', exact: true }).click();
            await page.getByRole('switch', { name: 'Check every model on every provider' }).click();
            await expect(page.locator('[data-model-eval-download]')).toContainText('2 models are not installed yet: a download of about 1.3 GB.');
            await expect(page.locator('[data-model-eval-skipped]')).toBeVisible();
            // Every finding of any impact inside the page, not only the serious ones.
            const results = await new AxeBuilder({ page }).include('[data-model-evaluation]').analyze();
            expect(results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(' | ')}`)).toEqual([]);
            const document = await new AxeBuilder({ page }).analyze();
            expect(document.violations.filter((violation) => violation.impact === 'serious' || violation.impact === 'critical').map((violation) => violation.id)).toEqual([]);
        });
    }
}

test('the page names each thing once, in sentence case, with the kit and plain words', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await openEvaluation(page);
    await expect(page).toHaveTitle('Model evaluation · YA-WAMF');
    await expect(page.getByRole('heading', { name: 'Model evaluation', exact: true })).toHaveCount(1);
    await expect(page.getByRole('heading', { level: 2 })).toHaveText(['Start an evaluation', 'Results', 'Provider checks']);
    const table = page.getByRole('region', { name: 'Results' }).getByRole('table');
    // Models carry the names Settings shows; the identifier is in the downloaded files only.
    await expect(table.getByRole('rowheader').first()).toHaveText('ConvNeXt Large (High Accuracy)');
    await expect(page.locator('[data-model-evaluation]')).not.toContainText(/convnext_large_inat21|small_birds/);
    await expect(table.getByRole('columnheader')).toHaveText([
        'Model', 'First guess right', 'Right in top three', 'Common feeder birds', 'Birds near you',
        'Species it can name', 'Average time', 'Slow photos', 'Ran on'
    ]);
    await expect(table.getByRole('row', { name: /Small Birds/ }).first()).toContainText('115 of 141');
    await expect(table).toContainText('Needs a look');
    await expect(table).toContainText('Worth a check');
    await expect(table).toContainText('Cannot name 26 of the 141 test species');
    await expect(page.locator('[data-model-eval-facts]')).toHaveText('141 species · 423 photos · Region GB-ENG · 16 minutes');
    await expect(page.locator('[data-model-eval-skipped]')).toContainText('EVA-02 Large (Elite Accuracy)');
    await expect(page.locator('[data-model-eval-skipped]')).toContainText('Use Repair download for this model in Settings → Models.');
    await expect(page.getByLabel('Evaluation', { exact: true }).locator('option')).toHaveText(['14/11/2026 08:15', '10/11/2026 07:00, stopped early']);

    const checks = page.getByRole('region', { name: 'Provider checks' }).getByRole('table');
    await expect(checks.getByRole('row', { name: /Small Birds/ })).toContainText('Did not load');
    await expect(checks.getByRole('row', { name: /Small Birds/ })).toContainText('Unusable output');
    await expect(checks.getByRole('row', { name: /Bird Crop Detector/ })).toContainText('Same boxes on all 27 photos');
    await expect(checks.getByRole('row', { name: /Bird Crop Detector/ })).toContainText('Not tested');

    // At this width every model is one line, so the rows keep one height.
    const heights = await table.locator('tbody tr').filter({ has: page.getByRole('rowheader') }).evaluateAll((rows) => rows.map((row) => Math.round(row.getBoundingClientRect().height)));
    // A row without a note carries the hairline that its note row otherwise does: one pixel.
    expect(Math.max(...heights) - Math.min(...heights), JSON.stringify(heights)).toBeLessThanOrEqual(1);
    expect(Math.max(...heights)).toBeLessThan(40);
    // The downloads are quiet text actions on one line.
    const tops = await page.getByRole('group', { name: 'Download the results' }).getByRole('button').evaluateAll((buttons) => buttons.map((button) => Math.round(button.getBoundingClientRect().top)));
    expect(tops).toHaveLength(5);
    expect(new Set(tops).size).toBe(1);
    await expect(page.locator('[data-model-evaluation]')).not.toContainText('Container image');

    // One sentence opens the page; the rest waits behind "How this works".
    const start = page.getByRole('region', { name: 'Start an evaluation' });
    await expect(start.locator('p')).toHaveCount(1);
    await expect(page.getByText('Each column is explained under How this works.')).toBeVisible();
    const how = page.getByRole('button', { name: 'How this works', exact: true });
    await expect(how).toHaveAttribute('aria-expanded', 'false');
    await how.focus();
    await page.keyboard.press('Enter');
    await expect(how).toHaveAttribute('aria-expanded', 'true');
    await expect(start.getByText('The time that 19 in 20 photos stayed under.')).toBeVisible();
    await expect(start.getByText('The photos are not from your feeder.', { exact: false })).toBeVisible();
    await how.click();
    await expect(start.locator('p')).toHaveCount(1);

    // A result is ordinary ink beside a status dot, so nothing in the table reads as a link.
    const sameCell = checks.getByRole('cell', { name: 'Same on all 24 photos' }).first();
    const ink = await sameCell.evaluate((cell) => getComputedStyle(cell).color);
    expect(ink).toBe(await checks.getByRole('cell', { name: 'Not tested' }).first().evaluate((cell) => getComputedStyle(cell).color));
    await expect(sameCell.locator('span[aria-hidden="true"]')).toHaveCount(1);
    // Delete is a quiet action at the right of the Results header.
    const results = page.getByRole('region', { name: 'Results' });
    const heading = await results.getByRole('heading', { level: 2 }).boundingBox();
    const remove = await results.getByRole('button', { name: 'Delete this evaluation', exact: true }).boundingBox();
    expect(remove && heading && remove.x > heading.x + heading.width).toBe(true);
    expect(remove && heading && Math.abs(remove.y + remove.height / 2 - (heading.y + heading.height / 2))).toBeLessThan(12);

    const page_ = page.locator('[data-model-evaluation]');
    await expect(page_).not.toContainText(/results\.jsonl|Sweep|artifact|top-1|NaN|baseline/i);
    // No tooltip-only explanation, and no symbol standing in for a word.
    expect(await page_.locator('[title]').count()).toBe(0);
    await expect(page_).not.toContainText(/[✓✗⚠]/u);
    // The header's Refresh re-reads the page, as on the other pages.
    const listed = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith('/model-eval/runs'));
    await page.getByRole('button', { name: 'Refresh', exact: true }).click();
    await listed;
});

test('checking every model states the download first and asks before it starts', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const posts: unknown[] = [];
    await openEvaluation(page);
    await page.route(RUNS, (route: Route) => {
        if (route.request().method() !== 'POST') return route.fallback();
        posts.push(route.request().postDataJSON());
        return route.fulfill({ status: 500, body: 'Internal Server Error' });
    });
    const options = page.getByRole('button', { name: 'Show evaluation options', exact: true });
    await expect(options).toHaveAttribute('aria-expanded', 'false');
    await options.focus();
    await page.keyboard.press('Enter');
    // The same control now says what pressing it again does.
    await expect(page.getByRole('button', { name: 'Hide evaluation options', exact: true })).toHaveAttribute('aria-expanded', 'true');
    const everyModel = page.getByRole('switch', { name: 'Check every model on every provider' });
    await expect(page.getByText('Models you have not installed are downloaded first and stay installed.', { exact: false })).toBeVisible();
    await everyModel.focus();
    await page.keyboard.press('Space');
    await expect(everyModel).toHaveAttribute('aria-checked', 'true');
    await expect(page.locator('[data-model-eval-download]')).toContainText('2 models are not installed yet: a download of about 1.3 GB.');

    await page.getByRole('button', { name: 'Start evaluation', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Download 2 models?');
    await expect(dialog).toContainText('2 models are not installed yet: a download of about 1.3 GB.');
    await expect(dialog).toContainText('The download may take a while, depending on your connection. Downloaded models stay on disk until you delete their files in Settings → Models.');
    await dialog.getByRole('button', { name: 'Go back', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(posts).toEqual([]);

    await page.getByRole('button', { name: 'Start evaluation', exact: true }).click();
    await page.getByRole('alertdialog').getByRole('button', { name: 'Download and start', exact: true }).click();
    await expect(page.getByRole('alert').filter({ hasText: 'The evaluation did not start.' })).toBeVisible();
    expect(posts).toEqual([expect.objectContaining({ sweep_devices: true, include_per_image: false })]);
});

test('a failure is shown by its cause and next step, and nothing an exception said reaches the page', async ({ page }) => {
    const LEAK = 'Traceback 0x7f3a /config/models/x.onnx';
    await page.route(EVAL_API, async (route) => {
        const path = new URL(route.request().url()).pathname;
        if (path.endsWith('/runs')) return route.fulfill({ json: { active: null, runs: [
            { run_id: 'stopped-known', status: 'complete', error_code: 'no_test_photos' },
            { run_id: 'stopped-unknown', status: 'complete', error_code: `ValueError: ${LEAK}` }
        ] } });
        if (path.endsWith('/device_matrix.json')) {
            return route.fulfill({ json: { ...compatibilityMatrix, models: {
                dinov2_location: { error: `provider_sweep_failed: ${LEAK}` },
                small_birds: { error: 'activation_failed' },
                odd_one: { error: LEAK }
            } } });
        }
        // Fields a server might still send, or an older summary might hold, are not read.
        const stray = { error: LEAK, detail: LEAK, message: LEAK };
        if (path.endsWith('/runs/stopped-known')) {
            return route.fulfill({ json: {
                run_id: 'stopped-known', error_code: 'no_test_photos', ...stray, available_artifacts: ['summary.json', 'device_matrix.json'],
                models: [{ ...accuracyModel, warnings: [{ code: 'provider_validation_failed', message: LEAK, severity: 'critical' }] }],
                skipped_models: [{ model_id: 'eva02', reason: 'reload_failed', ...stray }, { model_id: 'rope', reason: LEAK }]
            } });
        }
        return route.fulfill({ json: { run_id: 'stopped-unknown', error_code: `ValueError: ${LEAK}`, ...stray, models: [], available_artifacts: [] } });
    });
    await openFixture(page);
    const stoppedBox = page.locator('[data-model-eval-stopped]');
    await expect(stoppedBox).toContainText('This evaluation stopped before it finished, so some models may be missing.');
    await expect(stoppedBox).toContainText('No test photo could be fetched from iNaturalist or Wikimedia Commons. Check the internet connection, then start again.');
    const skipped = page.locator('[data-model-eval-skipped]');
    await expect(skipped).toContainText('It could not be loaded. Use Repair download for this model in Settings → Models; if that does not help, the container logs name the cause.');
    await expect(skipped).toContainText('It was skipped for a reason this page cannot name. The container logs name the cause.');
    await expect(page.getByRole('table').first()).toContainText('No provider gave usable answers that matched the CPU.');
    const checks = page.getByRole('region', { name: 'Provider checks' });
    await expect(checks).toContainText('The check failed before any provider gave a result. Run it again; if it fails again, the container logs name the cause.');
    await expect(checks).toContainText('It could not be loaded, so no provider was checked. Use Repair download for this model in Settings → Models.');
    await expect(checks).toContainText('It was not checked, for a reason this page cannot name. The container logs name the cause.');
    await expect(page.locator('body')).not.toContainText(/Traceback|0x7f3a|x\.onnx|ValueError|provider_sweep_failed|activation_failed|reload_failed/);

    await page.getByLabel('Evaluation', { exact: true }).selectOption('stopped-unknown');
    await expect(stoppedBox).toContainText('It stopped on an error this page cannot name. Start it again; if it stops again, the container logs name the cause.');
    await expect(page.locator('body')).not.toContainText(/Traceback|0x7f3a|ValueError/);
});

test('a refused request names its cause without repeating what the server said', async ({ page }) => {
    await page.route(EVAL_API, async (route) => {
        const request = route.request();
        if (request.method() === 'POST') return route.fulfill({ status: 422, json: { detail: 'Traceback 0x7f3a in start_run' } });
        return route.fulfill({ json: { active: null, runs: [] } });
    });
    await openFixture(page);
    await page.getByRole('button', { name: 'Start evaluation', exact: true }).click();
    const alert = page.getByRole('alert');
    await expect(alert).toContainText('The evaluation did not start.');
    await expect(alert).toContainText('YA-WAMF refused the request. Refresh the page and try again; if it is refused again, the container logs name the cause.');
    await expect(page.locator('body')).not.toContainText(/Traceback|0x7f3a|start_run/);
});

for (const { name, registry, line } of [
    {
        name: 'some sizes are not known',
        registry: [...REGISTRY, { id: 'bundled', name: 'Bundled', file_size_mb: 0 }],
        line: '3 models are not installed yet. 1 of them has no known size; the rest are a download of about 1.3 GB.'
    },
    {
        name: 'no size is known',
        registry: REGISTRY.map((model) => ({ ...model, file_size_mb: 0 })),
        line: '2 models are not installed yet. Their size is not known.'
    }
]) {
    test(`the download is stated honestly when ${name}, and the question says it takes time and stays on disk`, async ({ page }) => {
        await page.setViewportSize({ width: 1440, height: 900 });
        await openEvaluation(page, 'light', { ...withEvaluation, '/api/models/available': registry });
        await page.getByRole('button', { name: 'Show evaluation options', exact: true }).click();
        await page.getByRole('switch', { name: 'Check every model on every provider' }).click();
        const stated = page.locator('[data-model-eval-download]');
        await expect(stated).toContainText(line);
        await expect(stated).toContainText('The download may take a while, depending on your connection. Downloaded models stay on disk until you delete their files in Settings → Models.');
        await expect(stated).not.toContainText(/\b0 (MB|GB)\b/);
        await page.getByRole('button', { name: 'Start evaluation', exact: true }).click();
        const dialog = page.getByRole('alertdialog');
        await expect(dialog).toContainText(line);
        await expect(dialog).toContainText('The download may take a while, depending on your connection.');
        await expect(dialog).toContainText('stay on disk until you delete their files in Settings → Models');
        await expect(dialog).not.toContainText(/\b0 (MB|GB)\b/);
        await dialog.getByRole('button', { name: 'Go back', exact: true }).click();
    });
}

test('deleting an evaluation asks first, names it, and says it cannot be undone', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    const deleted: string[] = [];
    await openEvaluation(page);
    await page.route(`**/api/diagnostics/model-eval/runs/${RUN_ID}`, (route: Route) => {
        if (route.request().method() !== 'DELETE') return route.fallback();
        deleted.push(RUN_ID);
        return route.fulfill({ status: 404, json: { detail: 'run not found or in progress' } });
    });
    await page.getByRole('button', { name: 'Delete this evaluation', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Delete this evaluation?');
    await expect(dialog).toContainText('The results and files of the evaluation from 14/11/2026 08:15 are removed from the server. This cannot be undone.');
    await dialog.getByRole('button', { name: 'Delete evaluation', exact: true }).click();
    expect(deleted).toEqual([RUN_ID]);
    const alert = page.getByRole('alert').filter({ hasText: 'The evaluation was not deleted.' });
    await expect(alert).toContainText('It is no longer on the server. Refresh the page to see what is there.');
});

test('a German owner gets a German page that fits a phone without scrolling sideways', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await replayFeeder(page, 'light', withEvaluation);
    await page.goto('/diagnostics/model-eval');
    await expect(page.getByRole('heading', { level: 1, name: 'Modellbewertung', exact: true })).toBeVisible({ timeout: 15_000 });
    await settled(page);
    await page.getByRole('button', { name: 'Optionen für die Bewertung anzeigen', exact: true }).click();
    await page.getByRole('switch', { name: 'Jedes Modell auf jedem Anbieter prüfen' }).click();
    await expect(page.locator('[data-model-eval-download]')).toContainText('2 Modelle sind noch nicht installiert: ein Download von etwa 1,3 GB.');
    await expect(page.locator('[data-model-eval-download]')).toContainText('Heruntergeladene Modelle bleiben auf der Festplatte, bis Sie ihre Dateien unter Einstellungen → Erkennung → Modelle löschen.');
    const content = page.locator('[data-model-evaluation]');
    await expect(content.getByRole('heading', { level: 2 })).toHaveText(['Bewertung starten', 'Ergebnisse', 'Anbieterprüfungen']);
    // On a phone the figures are a labelled list, not a table to scroll.
    await expect(content.getByRole('table')).toHaveCount(0);
    await expect(content).toContainText('Erste Vermutung richtig');
    await expect(content).toContainText('90,0 %');
    await expect(content).toContainText('141 Arten · 423 Fotos · Region GB-ENG · 16 Minuten');
    // A fact wraps only at a separator, never inside itself.
    const factLines = await content.locator('[data-model-eval-facts] span.whitespace-nowrap').evaluateAll((facts) => facts.map((fact) => fact.getClientRects().length));
    expect(factLines).toEqual([1, 1, 1, 1]);
    await expect(content).not.toContainText(/\b(Start an|Results|Download the|Evaluation|First guess|Provider checks|Not tested|Delete this|Summary|Problem:|photos)\b/);
    expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(0);
});

declare global {
    interface Window { modelEvalShifts?: number[] }
}

for (const { device, viewport, budget } of [
    { device: 'desktop', viewport: { width: 1280, height: 800 }, budget: 0.05 },
    { device: 'phone', viewport: { width: 390, height: 844 }, budget: 0.1 }
]) {
    test(`a cold load holds still on a ${device} while the evaluations are read`, async ({ page }) => {
        await page.setViewportSize(viewport);
        await page.addInitScript(() => {
            window.modelEvalShifts = [];
            new PerformanceObserver((list) => {
                for (const entry of list.getEntries() as (PerformanceEntry & { value: number; hadRecentInput: boolean })[]) {
                    if (!entry.hadRecentInput) window.modelEvalShifts?.push(entry.value);
                }
            }).observe({ type: 'layout-shift', buffered: true });
        });
        await replayFeeder(page, 'light', withEvaluation);
        await page.route(EVAL_API, async (route: Route) => {
            await new Promise((resolve) => setTimeout(resolve, 1_200));
            return route.fallback();
        });
        await page.goto('/diagnostics/model-eval');
        await expect(page.getByRole('region', { name: 'Provider checks' }).first()).toBeVisible({ timeout: 15_000 });
        await settled(page);
        const shifts = await page.evaluate(() => window.modelEvalShifts ?? []);
        expect(shifts.reduce((sum, shift) => sum + shift, 0), JSON.stringify(shifts)).toBeLessThanOrEqual(budget);
    });
}

test('Settings opens the page from the Models tab, where models are chosen', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 900 });
    await replayFeeder(page, 'light', withEvaluation);
    await page.goto('/settings/models');
    const link = page.getByRole('link', { name: 'Open model evaluation', exact: true });
    await expect(link).toBeVisible({ timeout: 15_000 });
    await expect(link).toHaveAttribute('href', '/diagnostics/model-eval');
    await link.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('heading', { level: 1, name: 'Model evaluation', exact: true })).toBeVisible({ timeout: 15_000 });
    await expect(page).toHaveURL(/\/diagnostics\/model-eval$/);
});
