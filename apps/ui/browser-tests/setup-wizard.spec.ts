import { test, expect, type Page, type Route } from '@playwright/test';

// The real wizard (FirstRunWizard / WizardShell, the shared store and the typed API
// client) against a stateful fake of the backend routes it calls. The fake mirrors the
// server contract the wizard depends on: partial settings writes, the activation gate
// (validated models only, recommended provider saved on activation), and the
// compatibility-only evaluation run with its device matrix.

const DINO = 'dinov2_b14_inat21_metadata_336';
const MOBILENET = 'mobilenet_v2_birds';
const BROKEN = 'broken_install';
const RUN_ID = '20261010-120000';
// Fictional mid-ocean coordinates: never a real feeder.
const LAT = '12.5';
const LON = '-45.25';

type Json = Record<string, unknown>;

const PROVIDER_ORDER = ['intel_npu', 'intel_gpu', 'intel_cpu', 'cpu'];

function metadata(id: string, overrides: Json = {}): Json {
    return {
        id, name: id, description: 'Fixture classifier', architecture: 'fixture', accuracy_tier: 'Experimental',
        download_url: `https://example.invalid/${id}.onnx`, labels_url: '', file_size_mb: 10,
        inference_speed: 'Measured per host', recommended_for: 'Fixture hosts.', taxonomy_scope: 'birds_only',
        tier: 'small', artifact_kind: 'classifier', runtime: 'onnx', status: 'stable',
        supported_inference_providers: ['cpu', 'intel_cpu'],
        ...overrides
    };
}

const MODELS: Record<string, Json> = {
    [MOBILENET]: metadata(MOBILENET, { name: 'MobileNet V2 birds', tier: 'cpu_only' }),
    [DINO]: metadata(DINO, {
        name: 'DINOv2 B/14 with location', tier: 'large', status: 'experimental', taxonomy_scope: 'wildlife_wide',
        estimated_ram_mb: 2048, file_size_mb: 456.5,
        candidate_inference_providers: ['cpu', 'intel_cpu', 'cuda', 'intel_gpu', 'intel_npu'],
        preprocessing: { metadata_input: 'inat2021_location_v1' }
    }),
    [BROKEN]: metadata(BROKEN, { name: 'Broken install', tier: 'medium' })
};

interface InstalledEntry {
    id: string;
    ready: boolean;
    reason: string;
    validated: boolean;
    validated_inference_providers: string[];
    provider_preference_order: string[];
    preferred_inference_provider: string | null;
}

interface RecordedRequest {
    method: string;
    path: string;
    body: Json | null;
}

interface FakeOptions {
    firstRun?: boolean;
    activeModelId?: string;
    installed?: Partial<InstalledEntry>[];
    settings?: Json;
}

class FakeBackend {
    needsInitialSetup: boolean;
    authEnabled = false;
    activeModelId: string;
    installed: InstalledEntry[];
    settings: Json;
    requests: RecordedRequest[] = [];
    unexpected: string[] = [];
    allowExtraReads = false;
    downloadDone = false;
    evalState: 'idle' | 'running' | 'done' | 'error' = 'idle';
    evalError = '';
    evalFailedProviders: string[] = [];
    evalModelId = '';
    activationError: string | null = null;
    settingsError: string | null = null;
    downloadError: string | null = null;

    constructor(options: FakeOptions = {}) {
        this.needsInitialSetup = options.firstRun ?? false;
        this.activeModelId = options.activeModelId ?? MOBILENET;
        this.installed = (options.installed ?? [{ id: MOBILENET }]).map((entry) => ({
            ready: true,
            reason: 'ready',
            validated: true,
            validated_inference_providers: ['cpu', 'intel_cpu'],
            provider_preference_order: ['intel_cpu', 'cpu'],
            preferred_inference_provider: 'intel_cpu',
            id: '',
            ...entry
        }));
        this.settings = {
            frigate_url: '', mqtt_server: '', mqtt_port: 1883, mqtt_auth: false, mqtt_username: '',
            cameras: [], inference_provider: 'auto', classification_threshold: 0.6,
            location_latitude: null, location_longitude: null, location_automatic: true,
            birdweather_station_token: '***REDACTED***', media_cache_high_quality_event_snapshots: true,
            birdnet_enabled: false, birdnet_url: '', ebird_enabled: false, inaturalist_enabled: false,
            birdweather_enabled: false, llm_enabled: false, telemetry_enabled: false,
            ...options.settings
        };
    }

    posts(path: string): Json[] {
        return this.requests.filter((r) => r.method === 'POST' && r.path === path).map((r) => r.body ?? {});
    }

    settingsWrites(): Json[] {
        return this.posts('/api/settings');
    }

    requestIndex(predicate: (request: RecordedRequest) => boolean): number {
        return this.requests.findIndex(predicate);
    }

    finishEval(failedProviders: string[] = []): void {
        this.evalFailedProviders = failedProviders;
        this.evalState = 'done';
        const passed = PROVIDER_ORDER.filter((p) => !failedProviders.includes(p));
        const entry = this.installed.find((m) => m.id === this.evalModelId);
        if (entry) {
            entry.validated = true;
            entry.validated_inference_providers = [...passed].reverse();
            entry.provider_preference_order = passed;
            entry.preferred_inference_provider = passed[0] ?? null;
        }
    }

    failEval(message: string): void {
        this.evalState = 'error';
        this.evalError = message;
    }

    private status(): Json {
        const active = this.installed.find((m) => m.id === this.activeModelId);
        return {
            loaded: true, error: null, labels_count: 100, enabled: true,
            active_model_id: this.activeModelId, effective_model_id: this.activeModelId,
            image_flavor: 'intel', runtime_source: 'worker',
            available_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            host_available_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            packaged_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            intel_gpu_available: true, intel_npu_available: true, cuda_available: false,
            selected_provider: this.settings.inference_provider, active_provider: 'intel_cpu',
            provider_preference_order: active?.provider_preference_order ?? [],
            active_model_validated_providers: active?.validated_inference_providers ?? [],
            validated_provider_preference_order: active?.provider_preference_order ?? []
        };
    }

    private installedResponse(): Json[] {
        return this.installed.map((m) => ({
            ...m,
            path: `/data/models/${m.id}/model.onnx`,
            labels_path: `/data/models/${m.id}/labels.txt`,
            is_active: m.id === this.activeModelId,
            validation_reason: m.validated ? 'validated' : 'not_validated',
            metadata: MODELS[m.id]
        }));
    }

    private setupState(): Json {
        const s = this.settings;
        const cameras = (s.cameras as string[]) ?? [];
        return {
            initial_setup_complete: !this.needsInitialSetup,
            sections: [
                { id: 'account', status: this.needsInitialSetup ? 'attention' : 'ok', detail_code: this.authEnabled ? 'account_password_protected' : 'account_auth_disabled' },
                s.frigate_url && s.mqtt_server
                    ? { id: 'connection', status: 'ok', detail_code: 'connection_ready', detail_values: { url: String(s.frigate_url) } }
                    : { id: 'connection', status: 'attention', detail_code: 'connection_missing', detail_values: { items: 'frigate_url,mqtt_broker' } },
                cameras.length
                    ? { id: 'cameras', status: 'ok', detail_code: 'cameras_count', detail_values: { count: cameras.length } }
                    : { id: 'cameras', status: 'ok', detail_code: 'cameras_all' },
                { id: 'model', status: 'ok', detail_code: 'model_selected', detail_values: { model: String(MODELS[this.activeModelId]?.name ?? this.activeModelId) }, detail: this.activeModelId },
                { id: 'quality', status: 'optional', detail_code: s.media_cache_high_quality_event_snapshots ? 'quality_best' : 'quality_standard' },
                { id: 'integrations', status: 'optional', detail_code: 'integrations_none' }
            ]
        };
    }

    private matrix(): Json {
        const latency: Record<string, number> = { intel_npu: 41.6, intel_gpu: 63.2, intel_cpu: 180.4 };
        const providers: Json = { cpu: { compiles: true, ok: true, baseline: true, images_evaluated: 24 } };
        for (const provider of ['intel_cpu', 'intel_gpu', 'intel_npu']) {
            const failed = this.evalFailedProviders.includes(provider);
            providers[provider] = failed
                ? { compiles: false, ok: false, error: 'compile failed' }
                : { compiles: true, ok: true, finite: true, matches_cpu: true, images_compared: 24, latency_ms: latency[provider] };
        }
        const passed = PROVIDER_ORDER.filter((p) => !this.evalFailedProviders.includes(p));
        return {
            run_id: RUN_ID, generated_at: '2026-10-10T12:05:00Z', providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
            devices: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'], image_count: 24,
            models: { [this.evalModelId]: { baseline_provider: 'cpu', best_provider: passed[0], providers } }
        };
    }

    async handle(route: Route): Promise<void> {
        const request = route.request();
        const url = new URL(request.url());
        const path = url.pathname;
        const method = request.method();
        let body: Json | null = null;
        try {
            body = request.postDataJSON() as Json | null;
        } catch {
            body = null;
        }
        this.requests.push({ method, path, body });
        const json = (payload: unknown, status = 200) => route.fulfill({ status, json: payload });

        if (path === '/api/auth/status') {
            return json({
                auth_required: this.authEnabled, public_access_enabled: false, is_authenticated: true,
                needs_initial_setup: this.needsInitialSetup, username: 'admin'
            });
        }
        if (path === '/api/auth/initial-setup' && method === 'POST') {
            this.needsInitialSetup = false;
            this.authEnabled = Boolean(body?.enable_auth);
            return json({ status: 'ok', access_token: this.authEnabled ? 'fixture-owner-session' : null, expires_in_hours: 24 });
        }
        if (path === '/api/auth/session-cookie') return json({ status: 'ok' });
        if (path === '/api/setup/state') return json(this.setupState());
        if (path === '/api/settings' && method === 'GET') return json(this.settings);
        if (path === '/api/settings' && method === 'POST') {
            if (this.settingsError) return json({ detail: this.settingsError }, 500);
            this.settings = { ...this.settings, ...(body ?? {}) };
            return json({ status: 'success' });
        }
        if (path === '/api/frigate/test') return json({ status: 'ok', version: '0.16.0' });
        if (path === '/api/settings/mqtt/test-publish') return json({ status: 'ok', message: 'Test message published' });
        if (path === '/api/events/filters') return json({ cameras: ['feeder'], species: [] });
        if (path === '/api/audio/sources') return json([]);
        if (path === '/api/frigate/config') return json({ cameras: { feeder: {} } });
        if (path === '/api/backfill/status') return json(null);
        if (path === '/api/backfill/async' && method === 'POST') return json({ id: 'history-job', status: 'running', processed: 0, total: 20, message: 'Scanning Frigate event history' });
        if (path.startsWith('/api/frigate/camera/')) return route.fulfill({ status: 404, body: '' });
        if (path === '/api/classifier/status') return json(this.status());
        if (path === '/api/models/available') return json([MODELS[MOBILENET], MODELS[DINO], MODELS[BROKEN]]);
        if (path === '/api/models/installed') return json(this.installedResponse());

        const download = path.match(/^\/api\/models\/([^/]+)\/download$/);
        if (download && method === 'POST') return json({ status: 'pending', message: 'Download started' });
        const downloadStatus = path.match(/^\/api\/models\/download-status\/([^/]+)$/);
        if (downloadStatus) {
            const id = decodeURIComponent(downloadStatus[1]);
            if (this.downloadError) return json({ model_id: id, status: 'error', error: this.downloadError, progress: 0 });
            if (!this.downloadDone) return json({ model_id: id, status: 'downloading', progress: 48 });
            const existing = this.installed.find((m) => m.id === id);
            if (existing) {
                existing.ready = true;
                existing.reason = 'ready';
            } else {
                this.installed.push({
                    id, ready: true, reason: 'ready', validated: false,
                    validated_inference_providers: [], provider_preference_order: [], preferred_inference_provider: null
                });
            }
            return json({ model_id: id, status: 'completed', progress: 100 });
        }
        const activate = path.match(/^\/api\/models\/([^/]+)\/activate$/);
        if (activate && method === 'POST') {
            const target = this.installed.find((m) => m.id === activate[1]);
            if (!target) return json({ detail: 'Model not installed' }, 404);
            if (!target.validated) {
                return json({ detail: 'This model has not been validated on your hardware yet. Run validation before selecting it.' }, 409);
            }
            if (this.activationError) return json({ detail: this.activationError }, 500);
            this.activeModelId = target.id;
            this.settings = { ...this.settings, inference_provider: target.preferred_inference_provider ?? 'auto' };
            return json({ status: 'success', message: `Model ${target.id} activated` });
        }

        if (path === '/api/diagnostics/model-eval/runs' && method === 'POST') {
            this.evalState = 'running';
            this.evalModelId = ((body?.model_ids as string[]) ?? [])[0] ?? '';
            return json({ run_id: RUN_ID });
        }
        if (path === '/api/diagnostics/model-eval/runs') {
            return json({
                active: this.evalState === 'running'
                    ? { run_id: RUN_ID, phase: 'device_sweep', started_at: '2026-10-10T12:00:00Z', progress: { done: 2, total: 5, label: 'Checking Intel GPU' } }
                    : null,
                runs: []
            });
        }
        if (path === `/api/diagnostics/model-eval/runs/${RUN_ID}`) {
            if (this.evalState === 'running') return json({ run_id: RUN_ID, finished_at: null });
            if (this.evalState === 'error') return json({ run_id: RUN_ID, finished_at: null, error: this.evalError });
            const passed = PROVIDER_ORDER.filter((p) => !this.evalFailedProviders.includes(p));
            return json({
                run_id: RUN_ID, finished_at: '2026-10-10T12:05:00Z',
                models: [{
                    model_id: this.evalModelId, ready: true, active_provider: 'cpu', requested_provider: 'validation_sweep',
                    validated_providers: [...passed].reverse(), failed_providers: this.evalFailedProviders,
                    images_evaluated: 24, top1_accuracy: 0, top3_accuracy: 0, top5_accuracy: 0, abstention_rate: 0,
                    high_confidence_unknown_rate: 0, mean_latency_ms: 999, p50_latency_ms: 999, p95_latency_ms: 999,
                    shared_core_top1: 0, regional_top1: 0, warnings: []
                }]
            });
        }
        if (path === `/api/diagnostics/model-eval/runs/${RUN_ID}/device_matrix.json`) return json(this.matrix());

        if (this.allowExtraReads && method === 'GET') return json({});
        this.unexpected.push(`${method} ${path}`);
        return json({ detail: 'Not found' }, 404);
    }
}

async function openFixture(page: Page, fake: FakeBackend, settings = false): Promise<string[]> {
    fake.allowExtraReads = settings;
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname === '/health' || url.pathname.startsWith('/api/'), (route) => fake.handle(route));
    await page.goto(`/browser-tests/setup-wizard.html${settings ? '?settings=1' : ''}`);
    return errors;
}

function wizard(page: Page) {
    return page.getByRole('dialog', { name: 'Setup wizard' });
}

async function expectStep(page: Page, title: string): Promise<void> {
    await expect(wizard(page).getByRole('heading', { level: 2, name: title, exact: true })).toBeVisible();
}

async function openSectionFromReview(page: Page, sectionTitle: string): Promise<void> {
    await expectStep(page, 'Review setup');
    const row = wizard(page).getByRole('listitem').filter({ hasText: sectionTitle });
    await row.getByRole('button', { name: 'Review', exact: true }).click();
}

async function openRerun(page: Page, fake: FakeBackend): Promise<string[]> {
    const errors = await openFixture(page, fake);
    await page.getByRole('button', { name: 'Open setup wizard' }).click();
    await expectStep(page, 'Review setup');
    return errors;
}

const continueButton = (page: Page) => wizard(page).getByRole('button', { name: 'Continue', exact: true });
const modelSelect = (page: Page) => wizard(page).getByLabel('Model', { exact: true });
const providerSelect = (page: Page) => wizard(page).getByLabel('Inference Provider', { exact: true });
const latitude = (page: Page) => wizard(page).getByLabel('Latitude', { exact: true });
const longitude = (page: Page) => wizard(page).getByLabel('Longitude', { exact: true });
const validateButton = (page: Page) => wizard(page).getByRole('button', { name: 'Validate on my hardware' });

for (const importHistory of [false, true]) {
test(`first run walks every step to Finish with history import ${importHistory} and isolated settings saves`, async ({ page }) => {
    test.setTimeout(60_000);
    const fake = new FakeBackend({ firstRun: true });
    const errors = await openFixture(page, fake);

    await expectStep(page, 'Welcome to YA-WAMF');
    await wizard(page).getByRole('button', { name: 'Get started' }).click();

    await expectStep(page, 'Admin account & access');
    await wizard(page).getByLabel('Password', { exact: true }).fill('feeder2026');
    await wizard(page).getByLabel('Confirm password').fill('feeder2026');
    await continueButton(page).click();

    await expectStep(page, 'Frigate & MQTT connection');
    expect(fake.posts('/api/auth/initial-setup')).toEqual([{ username: 'admin', password: 'feeder2026', enable_auth: true }]);
    await expect(continueButton(page)).toBeDisabled();
    await wizard(page).getByLabel('Frigate URL').fill('http://frigate:5000');
    await wizard(page).getByLabel('MQTT broker').fill('mqtt');
    await wizard(page).getByRole('button', { name: 'Save & test connection' }).click();
    await expect(wizard(page).getByText('Connected to Frigate 0.16.0')).toBeVisible();
    await continueButton(page).click();

    await expectStep(page, 'Cameras & detection');
    await wizard(page).getByLabel('Cameras (comma-separated)').fill('feeder, nestbox');
    await continueButton(page).click();

    await expectStep(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await expect(wizard(page).getByText('Download and verify this model here before validating it on this hardware.')).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    await expect(wizard(page).getByRole('group', { name: 'Feeder location' })).toBeVisible();

    await wizard(page).getByRole('button', { name: 'Download model' }).click();
    await expect(wizard(page).getByRole('progressbar', { name: 'Download model' })).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    fake.downloadDone = true;
    await expect(wizard(page).getByText('Downloaded and verified.')).toBeVisible({ timeout: 10_000 });
    await expect(wizard(page).getByText('Validate this model on the current image and hardware before continuing.')).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();

    await latitude(page).fill(LAT);
    await longitude(page).fill(LON);
    await validateButton(page).click();
    await expect(wizard(page).getByRole('progressbar', { name: 'Validate on my hardware' })).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    await expect(modelSelect(page)).toBeDisabled();
    await expect(wizard(page).getByText('Leaving this step does not stop the check.', { exact: false })).toBeVisible();

    // The coordinates are saved before the check starts, so the check uses them.
    const locationWrite = fake.requestIndex((r) => r.path === '/api/settings' && r.method === 'POST' && r.body?.location_latitude !== undefined);
    const runStart = fake.requestIndex((r) => r.path === '/api/diagnostics/model-eval/runs' && r.method === 'POST');
    expect(locationWrite).toBeGreaterThanOrEqual(0);
    expect(locationWrite).toBeLessThan(runStart);
    expect(fake.requests[locationWrite].body).toEqual({ location_latitude: 12.5, location_longitude: -45.25 });
    expect(fake.requests[runStart].body).toMatchObject({ sweep_devices: true, compat_only: true, model_ids: [DINO] });

    fake.finishEval();
    await expect(wizard(page).getByText('Best validated provider: Intel NPU (OpenVINO), 42 ms per image')).toBeVisible({ timeout: 10_000 });
    await expect(wizard(page).getByText('It did not measure accuracy', { exact: false })).toBeVisible();
    await expect(wizard(page).getByText('999')).toHaveCount(0);
    await expect(providerSelect(page)).toHaveValue('intel_npu');
    await expect(continueButton(page)).toBeEnabled();
    await continueButton(page).click();

    await expectStep(page, 'Best available snapshots');
    expect(fake.posts(`/api/models/${DINO}/activate`)).toHaveLength(1);
    expect(fake.activeModelId).toBe(DINO);
    expect(fake.settings.inference_provider).toBe('intel_npu');
    expect(fake.settings.location_latitude).toBe(12.5);
    expect(fake.settings.location_longitude).toBe(-45.25);
    await continueButton(page).click();

    await expectStep(page, 'Integrations');
    await continueButton(page).click();
    await expectStep(page, 'Import existing detections');
    if (importHistory) {
        await wizard(page).getByRole('checkbox', { name: 'Import retained Frigate bird events' }).check();
        await wizard(page).getByText('Last 7 days', { exact: true }).click();
        await wizard(page).getByRole('button', { name: 'Import & continue' }).click();
    } else {
        await wizard(page).getByRole('button', { name: 'Continue without importing' }).click();
    }
    await expectStep(page, 'Share anonymous usage stats?');
    await continueButton(page).click();

    await expectStep(page, 'Review setup');
    await expect(wizard(page).getByRole('listitem').filter({ hasText: 'Classifier model & hardware' })).toContainText('DINOv2 B/14 with location');
    await wizard(page).getByRole('button', { name: 'Finish' }).click();
    await expect(page.getByRole('heading', { name: 'App opened' })).toBeVisible();
    await expect(wizard(page)).toHaveCount(0);

    expect(fake.settingsWrites()).toEqual([
        { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, mqtt_username: '' },
        { cameras: ['feeder', 'nestbox'] },
        { location_latitude: 12.5, location_longitude: -45.25 },
        { inference_provider: 'intel_npu' },
        { media_cache_high_quality_event_snapshots: true },
        { birdnet_enabled: false, birdnet_url: '', ebird_enabled: false, inaturalist_enabled: false, birdweather_enabled: false, llm_enabled: false },
        { telemetry_enabled: false }
    ]);
    expect(fake.settings.classification_threshold).toBe(0.6);
    expect(fake.settings.birdweather_station_token).toBe('***REDACTED***');
    expect(fake.requests.some((r) => r.path.endsWith('/cancel'))).toBe(false);
    expect(fake.posts('/api/backfill/async')).toEqual(importHistory ? [{ date_range: 'week' }] : []);
    expect(fake.unexpected).toEqual([]);
    expect(errors).toEqual([]);
});
}

test('a re-run edits one section and leaves every other setting alone', async ({ page }) => {
    const fake = new FakeBackend({ settings: { location_latitude: 10, location_longitude: 20, frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', cameras: ['feeder'] } });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await expectStep(page, 'Classifier model & hardware');
    await expect(modelSelect(page)).toHaveValue(MOBILENET);
    // Location input is offered only for a model that reads it.
    await expect(wizard(page).getByRole('group', { name: 'Feeder location' })).toHaveCount(0);
    await expect(providerSelect(page)).toHaveValue('auto');
    await providerSelect(page).selectOption('cpu');
    await continueButton(page).click();

    await expectStep(page, 'Review setup');
    expect(fake.settingsWrites()).toEqual([{ inference_provider: 'cpu' }]);
    expect(fake.posts(`/api/models/${MOBILENET}/activate`)).toEqual([]);

    await openSectionFromReview(page, 'Cameras & detection');
    await expect(wizard(page).getByLabel('Cameras (comma-separated)')).toHaveValue('feeder');
    await wizard(page).getByRole('button', { name: 'Back' }).click();
    await expectStep(page, 'Review setup');
    expect(fake.settingsWrites()).toEqual([{ inference_provider: 'cpu' }]);

    await wizard(page).getByRole('button', { name: 'Done' }).click();
    await expect(wizard(page)).toHaveCount(0);
    expect(fake.settings).toMatchObject({ location_latitude: 10, location_longitude: 20, classification_threshold: 0.6, cameras: ['feeder'] });
    expect(fake.unexpected).toEqual([]);
    expect(errors).toEqual([]);
});

test('feeder coordinates must be a whole valid pair; zero is valid and empty means no location', async ({ page }) => {
    const fake = new FakeBackend({
        activeModelId: DINO,
        installed: [{ id: MOBILENET }, { id: DINO, validated_inference_providers: ['cpu', 'intel_npu'], provider_preference_order: ['intel_npu', 'cpu'], preferred_inference_provider: 'intel_npu' }],
        settings: { location_latitude: 10, location_longitude: 20, inference_provider: 'intel_npu' }
    });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await expect(modelSelect(page)).toHaveValue(DINO);
    await expect(latitude(page)).toHaveValue('10');
    await expect(longitude(page)).toHaveValue('20');
    await expect(wizard(page).getByText('Validating or continuing saves these coordinates first', { exact: false })).toBeVisible();

    await latitude(page).fill('');
    await expect(wizard(page).getByRole('alert').filter({ hasText: 'Enter both latitude and longitude, or leave both empty.' })).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    await expect(validateButton(page)).toBeDisabled();

    await latitude(page).fill('91');
    await expect(wizard(page).getByRole('alert').filter({ hasText: 'Latitude must be −90 to 90 and longitude −180 to 180.' })).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    await longitude(page).fill('-181');
    await latitude(page).fill('45');
    await expect(wizard(page).getByRole('alert').filter({ hasText: 'Latitude must be −90 to 90 and longitude −180 to 180.' })).toBeVisible();

    await latitude(page).fill('0');
    await longitude(page).fill('0');
    await expect(wizard(page).getByRole('alert')).toHaveCount(0);
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.settingsWrites()).toEqual([{ location_latitude: 0, location_longitude: 0 }]);
    expect(fake.posts(`/api/models/${DINO}/activate`)).toEqual([]);

    await openSectionFromReview(page, 'Classifier model & hardware');
    await expect(latitude(page)).toHaveValue('0');
    await latitude(page).fill('');
    await longitude(page).fill('');
    await expect(wizard(page).getByText('No location will be used: this model identifies birds without it.')).toBeVisible();
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.settingsWrites()).toEqual([
        { location_latitude: 0, location_longitude: 0 },
        { location_latitude: null, location_longitude: null }
    ]);
    expect(fake.settings.inference_provider).toBe('intel_npu');
    expect(errors).toEqual([]);
});

test('a failed check is said in words and keeps Continue disabled', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated: false, validated_inference_providers: [], provider_preference_order: [], preferred_inference_provider: null }] });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await expect(wizard(page).getByText('No location will be used: this model identifies birds without it.')).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    await validateButton(page).click();
    await expect(wizard(page).getByText('Continue is available when the check finishes.', { exact: false })).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    // Nothing to save: no location was entered and none was saved.
    expect(fake.settingsWrites()).toEqual([]);

    fake.failEval('The ONNX session could not be created on this host.');
    await expect(wizard(page).getByRole('alert').filter({ hasText: 'The ONNX session could not be created on this host.' })).toBeVisible({ timeout: 10_000 });
    await expect(continueButton(page)).toBeDisabled();
    await expect(validateButton(page)).toBeEnabled();
    expect(fake.posts(`/api/models/${DINO}/activate`)).toEqual([]);
    expect(errors).toEqual([]);
});

test('an explicit provider choice survives the check when it passes', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'], provider_preference_order: PROVIDER_ORDER, preferred_inference_provider: 'intel_npu' }] });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    // Activation saves the model's recommendation, so the form shows it rather than an Auto it would not keep.
    await expect(providerSelect(page)).toHaveValue('intel_npu');
    await providerSelect(page).selectOption('intel_gpu');
    await validateButton(page).click();
    fake.finishEval();
    await expect(wizard(page).getByText('Best validated provider: Intel NPU (OpenVINO), 42 ms per image')).toBeVisible({ timeout: 10_000 });
    await expect(providerSelect(page)).toHaveValue('intel_gpu');
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.activeModelId).toBe(DINO);
    expect(fake.settings.inference_provider).toBe('intel_gpu');
    expect(fake.settingsWrites()).toEqual([{ inference_provider: 'intel_gpu' }]);
    expect(errors).toEqual([]);
});

test('an explicit provider that fails the check is replaced and the change is explained', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'], provider_preference_order: PROVIDER_ORDER, preferred_inference_provider: 'intel_npu' }] });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await providerSelect(page).selectOption('intel_npu');
    await validateButton(page).click();
    fake.finishEval(['intel_npu']);
    await expect(wizard(page).getByText('Intel NPU (OpenVINO) did not pass the check for this model, so Intel GPU (OpenVINO) is selected instead.')).toBeVisible({ timeout: 10_000 });
    await expect(wizard(page).getByText('Failed: Intel NPU (OpenVINO)')).toBeVisible();
    await expect(providerSelect(page)).toHaveValue('intel_gpu');
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.settings.inference_provider).toBe('intel_gpu');
    expect(errors).toEqual([]);
});

test('a failed activation stays on the model step and can be retried', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated_inference_providers: ['cpu', 'intel_npu'], provider_preference_order: ['intel_npu', 'cpu'], preferred_inference_provider: 'intel_npu' }] });
    fake.activationError = 'The model files are locked by another process.';
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await latitude(page).fill(LAT);
    await longitude(page).fill(LON);
    await continueButton(page).click();
    await expect(wizard(page).getByRole('alert').filter({ hasText: 'The model files are locked by another process.' })).toBeVisible();
    await expectStep(page, 'Classifier model & hardware');
    expect(fake.activeModelId).toBe(MOBILENET);
    // The location was saved first; the provider is not written for a model that did not activate.
    expect(fake.settingsWrites()).toEqual([{ location_latitude: 12.5, location_longitude: -45.25 }]);

    fake.activationError = null;
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.activeModelId).toBe(DINO);
    expect(fake.settingsWrites()).toEqual([
        { location_latitude: 12.5, location_longitude: -45.25 },
        { inference_provider: 'intel_npu' }
    ]);
    expect(errors).toEqual([]);
});

for (const leave of ['Back', 'Skip'] as const) {
    test(`a check still running after ${leave} cannot change the wizard or the saved settings`, async ({ page }) => {
        const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated: false, validated_inference_providers: [], provider_preference_order: [], preferred_inference_provider: null }] });
        const errors = await openRerun(page, fake);
        await openSectionFromReview(page, 'Classifier model & hardware');
        await modelSelect(page).selectOption(DINO);
        await validateButton(page).click();
        await expect(wizard(page).getByRole('progressbar', { name: 'Validate on my hardware' })).toBeVisible();
        await wizard(page).getByRole('button', { name: leave === 'Skip' ? 'Skip step' : leave, exact: true }).click();
        await expectStep(page, 'Review setup');

        const requestsAtLeave = fake.requests.length;
        fake.finishEval();
        await page.waitForTimeout(4_500);
        const later = fake.requests.slice(requestsAtLeave);
        expect(later.filter((r) => r.path.startsWith('/api/diagnostics/model-eval'))).toEqual([]);
        expect(later.filter((r) => r.method === 'POST')).toEqual([]);
        expect(fake.requests.some((r) => r.path.endsWith('/cancel'))).toBe(false);
        await expectStep(page, 'Review setup');

        // Coming back reads the finished check from the server.
        await openSectionFromReview(page, 'Classifier model & hardware');
        await modelSelect(page).selectOption(DINO);
        await expect(continueButton(page)).toBeEnabled();
        expect(errors).toEqual([]);
    });
}

test('an incomplete install cannot be continued with and offers a fresh download', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: BROKEN, ready: false, reason: 'missing_labels', validated: true }] });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(BROKEN);
    await expect(wizard(page).getByText('This model install is incomplete.', { exact: false })).toBeVisible();
    await expect(continueButton(page)).toBeDisabled();
    await expect(wizard(page).getByRole('button', { name: 'Download model' })).toBeVisible();
    expect(errors).toEqual([]);
});

test('an explicit Auto choice is saved instead of the activation recommendation', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated_inference_providers: ['cpu', 'intel_npu'], provider_preference_order: ['intel_npu', 'cpu'], preferred_inference_provider: 'intel_npu' }] });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await providerSelect(page).selectOption('auto');
    await validateButton(page).click();
    fake.finishEval();
    await expect(wizard(page).getByText('Best validated provider: Intel NPU (OpenVINO), 42 ms per image')).toBeVisible({ timeout: 10_000 });
    await expect(providerSelect(page)).toHaveValue('auto');
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.settings.inference_provider).toBe('auto');
    expect(fake.settingsWrites()).toEqual([{ inference_provider: 'auto' }]);
    expect(errors).toEqual([]);
});

test('a failed location save prevents validation and keeps the entered coordinates for retry', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated: false }] });
    fake.settingsError = 'The configuration volume is read-only.';
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await latitude(page).fill(LAT);
    await longitude(page).fill(LON);
    await validateButton(page).click();
    await expect(wizard(page).getByRole('alert').filter({ hasText: fake.settingsError })).toBeVisible();
    expect(fake.posts('/api/diagnostics/model-eval/runs')).toEqual([]);
    expect(fake.settings.location_latitude).toBeNull();
    await expect(latitude(page)).toHaveValue(LAT);
    await expect(longitude(page)).toHaveValue(LON);
    fake.settingsError = null;
    await validateButton(page).click();
    await expect.poll(() => fake.posts('/api/diagnostics/model-eval/runs').length).toBe(1);
    expect(fake.settings.location_latitude).toBe(12.5);
    expect(fake.settings.location_longitude).toBe(-45.25);
    expect(errors).toEqual([]);
});

test('a failed download stays on the model step and can be retried', async ({ page }) => {
    const fake = new FakeBackend();
    fake.downloadError = 'Model checksum verification failed.';
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    await wizard(page).getByRole('button', { name: 'Download model' }).click();
    await expect(wizard(page).getByRole('alert').filter({ hasText: fake.downloadError })).toBeVisible({ timeout: 10_000 });
    await expect(continueButton(page)).toBeDisabled();
    expect(fake.posts(`/api/models/${DINO}/activate`)).toEqual([]);
    fake.downloadError = null;
    fake.downloadDone = true;
    await wizard(page).getByRole('button', { name: 'Download model' }).click();
    await expect(wizard(page).getByText('Downloaded and verified.')).toBeVisible({ timeout: 10_000 });
    await expect(continueButton(page)).toBeDisabled();
    expect(fake.posts(`/api/models/${DINO}/download`)).toHaveLength(2);
    expect(errors).toEqual([]);
});

test('a validation response already in flight cannot refresh a step after Back', async ({ page }) => {
    const fake = new FakeBackend({ installed: [{ id: MOBILENET }, { id: DINO, validated: false }] });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Classifier model & hardware');
    await modelSelect(page).selectOption(DINO);
    const held: { route?: Route } = {};
    await page.route(`**/api/diagnostics/model-eval/runs/${RUN_ID}`, route => { held.route = route; });
    await validateButton(page).click();
    await expect.poll(() => fake.evalState).toBe('running');
    fake.finishEval();
    await expect.poll(() => Boolean(held.route)).toBe(true);
    await wizard(page).getByRole('button', { name: 'Back', exact: true }).click();
    await expectStep(page, 'Review setup');
    const atLeave = fake.requests.length;
    if (!held.route) throw new Error('Validation response was not held');
    await held.route.fulfill({ json: { run_id: RUN_ID, finished_at: '2026-10-10T12:05:00Z', models: [] } });
    // Flush the resolved fetch and its continuations before checking for forbidden follow-up reads.
    await page.waitForTimeout(200);
    const later = fake.requests.slice(atLeave);
    expect(later.filter(r => r.path === '/api/models/installed' || r.path === '/api/classifier/status' || r.path.includes('device_matrix') || r.method === 'POST')).toEqual([]);
    await expectStep(page, 'Review setup');
    expect(errors).toEqual([]);
});

test('connection re-run preserves a saved MQTT password without posting its redaction', async ({ page }) => {
    const fake = new FakeBackend({ settings: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_auth: true, mqtt_username: 'feeder-reader', mqtt_password: '***REDACTED***' } });
    const errors = await openRerun(page, fake);
    await openSectionFromReview(page, 'Frigate & MQTT connection');
    await wizard(page).getByRole('button', { name: 'Save & test connection' }).click();
    await expect(wizard(page).getByText('Test message published', { exact: true })).toBeVisible();
    await continueButton(page).click();
    await expectStep(page, 'Review setup');
    expect(fake.settingsWrites()).toEqual([{ frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: true, mqtt_username: 'feeder-reader' }]);
    expect(fake.settings.mqtt_password).toBe('***REDACTED***');
    expect(fake.posts('/api/settings/mqtt/test-publish')).toEqual([{ server: 'mqtt', port: 1883, auth: true, username: 'feeder-reader', password: '' }]);
    expect(errors).toEqual([]);
});

for (const change of ['location', 'cameras', 'quality', 'integrations'] as const) {
    test(`wizard ${change} saves survive a later Settings save without losing unrelated edits`, async ({ page }) => {
        const fake = new FakeBackend({
            activeModelId: DINO,
            installed: [{ id: DINO, validated_inference_providers: ['cpu', 'intel_npu'], provider_preference_order: ['intel_npu', 'cpu'], preferred_inference_provider: 'intel_npu' }],
            settings: { inference_provider: 'intel_npu', location_latitude: 10, location_longitude: 20 }
        });
        // Settings reads some other panels during mount; this test exercises the real
        // model/location/cameras forms and intercepts those unrelated reads as empty.
        const errors = await openFixture(page, fake, true);
        const slider = page.locator('#confidence-threshold-slider');
        await expect(slider, JSON.stringify(errors)).toHaveValue('0.6');
        await slider.fill('0.75');
        await page.locator('[data-setup-wizard-action]:visible').click();
        if (change === 'location') {
            await openSectionFromReview(page, 'Classifier model & hardware');
            await latitude(page).fill(LAT);
            await longitude(page).fill(LON);
        } else if (change === 'cameras') {
            await openSectionFromReview(page, 'Cameras & detection');
            await wizard(page).getByLabel('Cameras (comma-separated)').fill('feeder, nestbox');
        } else if (change === 'quality') {
            await openSectionFromReview(page, 'Best available snapshots');
            await wizard(page).getByRole('checkbox', { name: 'Best available event snapshots' }).uncheck();
        } else {
            await openSectionFromReview(page, 'Integrations');
            await wizard(page).getByRole('checkbox', { name: /^eBird/ }).check();
        }
        await continueButton(page).click();
        await expectStep(page, 'Review setup');
        await wizard(page).getByRole('button', { name: 'Done', exact: true }).click();
        await expect(slider).toHaveValue('0.75');
        await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
        await expect.poll(() => fake.settingsWrites().length).toBeGreaterThan(1);
        const save = fake.settingsWrites().at(-1);
        expect(save?.classification_threshold).toBe(0.75);
        if (change === 'location') expect(save).toMatchObject({ location_latitude: 12.5, location_longitude: -45.25 });
        if (change === 'cameras') expect(save?.cameras).toEqual(['feeder', 'nestbox']);
        if (change === 'quality') expect(save?.media_cache_high_quality_event_snapshots).toBe(false);
        if (change === 'integrations') expect(save?.ebird_enabled).toBe(true);
        expect(errors).toEqual([]);
    });
}
