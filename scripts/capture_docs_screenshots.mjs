// Run from the repository root after starting the current UI on port 4189:
// APP_BRANCH=stable npm --prefix apps/ui run dev -- --host 127.0.0.1 --port 4189 --strictPort
// node scripts/capture_docs_screenshots.mjs
// Every API response is local and read-only. This never connects to a live server.
import { createRequire } from 'node:module';
import { readFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
const require = createRequire(resolve('apps/ui/package.json'));
const { chromium } = require('@playwright/test');
const base = process.env.DOCS_UI_URL ?? 'http://127.0.0.1:4189';
const baseUrl = new URL(base);
if (!['127.0.0.1', 'localhost'].includes(baseUrl.hostname) || !['http:', 'https:'].includes(baseUrl.protocol)
    || baseUrl.username || baseUrl.password || baseUrl.search || baseUrl.hash || baseUrl.pathname !== '/') {
    throw new Error('Documentation capture requires a local UI origin without credentials, a path, query or fragment');
}
const images = resolve('docs/images');
const gardenOnly = process.argv.includes('--garden-only');
const version = (await readFile('VERSION', 'utf8')).trim();
const catalog = JSON.parse(await readFile('scripts/fixtures/documentation-models.json', 'utf8'));
const DINO = 'dinov2_b14_inat21_metadata_336';
const runId = 'example-compatibility';
const settings = {
    garden_cameras: gardenOnly ? ['feeder'] : [], garden_motion_cameras: [], garden_labels: ['cat', 'dog'],
    garden_motion_confidence: 0.5, garden_automatic_naming: true, garden_naming_threshold: 0.8,
    beta_garden_animals: gardenOnly,
    frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883,
    mqtt_auth: true, mqtt_username: 'feeder', mqtt_password: '***REDACTED***',
    cameras: ['feeder'], classification_threshold: 0.6, classification_min_confidence: 0.6,
    inference_provider: 'intel_npu', image_execution_mode: 'subprocess',
    location_latitude: null, location_longitude: null, location_automatic: false,
    media_cache_high_quality_event_snapshots: true, media_cache_clips: true,
    media_cache_retention_days: 0, media_cache_per_species_minimum: 0,
    media_cache_per_species_maximum: 50, media_cache_max_size_mb: 2048,
    retention_days: 0, maintenance_max_concurrent: 1,
    auth_enabled: true, auth_username: 'admin', public_access_enabled: false,
    birdnet_enabled: true, birdnet_url: 'http://birdnet-go:8080',
    ebird_enabled: false, inaturalist_enabled: false, birdweather_enabled: false,
    llm_enabled: false, telemetry_enabled: false, notifications_filter_min_confidence: 0.7,
    appearance_color_theme: 'bluetit', appearance_font_theme: 'system',
};
const status = {
    loaded: true, enabled: true, error: null, labels_count: 10000,
    active_model_id: DINO, effective_model_id: DINO, runtime_source: 'worker',
    active_provider: 'intel_npu', selected_provider: 'intel_npu', inference_backend: 'openvino',
    image_execution_mode: 'subprocess', image_flavor: 'intel',
    available_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
    host_available_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
    packaged_inference_providers: ['cpu', 'intel_cpu', 'intel_gpu', 'intel_npu'],
    intel_gpu_available: true, intel_npu_available: true, cuda_available: false,
    active_model_validated_providers: ['cpu', 'intel_npu'],
    provider_preference_order: ['intel_npu', 'cpu'], validated_provider_preference_order: ['intel_npu', 'cpu'],
    host_device_eligibility: { verified_providers: ['cpu', 'intel_npu'] },
};
const matrix = {
    run_id: runId, image_flavor: 'intel', generated_at: '2026-10-10T16:49:09Z', image_count: 24,
    providers: ['cpu', 'intel_npu'], devices: ['cpu', 'intel_npu'],
    models: { [DINO]: { baseline_provider: 'cpu', best_provider: 'intel_npu', providers: {
        cpu: { compiles: true, ok: true, baseline: true, images_evaluated: 24 },
        intel_npu: { compiles: true, ok: true, finite: true, matches_cpu: true, images_compared: 24, latency_ms: 120.4 },
    } } },
};
const compatibility = {
    run_id: runId, finished_at: '2026-10-10T16:49:09Z', duration_seconds: 564,
    models: [{ model_id: DINO, active_provider: 'intel_npu', requested_provider: 'validation_sweep', ready: true,
        validated_providers: ['cpu', 'intel_npu'], failed_providers: [], images_evaluated: 24,
        top1_accuracy: 0, top3_accuracy: 0, top5_accuracy: 0, abstention_rate: 0, high_confidence_unknown_rate: 0,
        mean_latency_ms: 120.4, p50_latency_ms: 120.4, p95_latency_ms: 120.4, shared_core_top1: 0, regional_top1: 0, warnings: [] }],
};
const records = [
    { frigate_event: 'doc-dunnock', display_name: 'Prunella modularis', scientific_name: 'Prunella modularis', common_name: 'Dunnock', camera_name: 'feeder', detection_time: '2026-10-11T08:00:00Z', score: 0.96, has_clip: true },
    { frigate_event: 'doc-robin', display_name: 'Erithacus rubecula', scientific_name: 'Erithacus rubecula', common_name: 'European Robin', camera_name: 'feeder', detection_time: '2026-10-11T07:00:00Z', score: 0.57, has_clip: false },
];
const visits = records.map((record, i) => ({ visit_id: record.frigate_event, start_time: record.detection_time, end_time: record.detection_time, capture_count: i ? 1 : 3, best_score: record.score, needs_review: Boolean(i), audio_confirmed: false, representative: record, latest: record, peak_capture: null }));
const monthRecords = Array.from({ length: 12 }, (_,i) => ({ ...records[i % 2], frigate_event: `${records[i % 2].frigate_event}-month-${i}`, score: 0.96, detection_time: new Date(Date.parse('2026-10-11T08:00:00Z') - Math.floor(i / 2) * 86_400_000 - (i % 2) * 3_600_000).toISOString() }));
const speciesRows = records.map((r, i) => ({ species: r.scientific_name, common_name: r.common_name, scientific_name: r.scientific_name, window_count: i ? 6 : 8, window_visit_count: 6, window_prev_count: 0, window_prev_visit_count: 0, window_delta: 1, window_percent: 0, window_avg_confidence: r.score, window_camera_count: 1, window_first_seen: i ? '2026-10-06T07:00:00Z' : '2026-10-06T08:00:00Z', window_last_seen: r.detection_time, reported_nearby: true }));
const audioSummary = { total: 3, species_count: 1, source_count: 1, top_species: [{ species: 'European Robin', count: 3, avg_confidence: 0.93, max_confidence: 0.95, first_heard: '2026-10-11T07:30:00Z', last_heard: '2026-10-11T07:34:00Z' }], daily_counts: [{ date: '2026-10-11', count: 3 }], hourly_counts: Array.from({ length: 24 }, (_,hour) => ({ hour, count: hour === 8 ? 3 : 0 })), sources: [{ source_name: 'Garden microphone', count: 3, last_heard: '2026-10-11T07:34:00Z' }] };
const captured = [];
const errors = [];
const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 1800 }, locale: 'en-GB', timezoneId: 'Europe/London', deviceScaleFactor: 1, reducedMotion: 'reduce', serviceWorkers: 'block' });
await context.addInitScript(() => {
    document.addEventListener('DOMContentLoaded', () => document.documentElement.classList.add('dark', 'theme-bluetit'));
});
// Install first: handlers below may mock local API calls, and all other local
// assets fall through to Vite. No remote image, font or API may reach a host.
await context.route('**/*', route => new URL(route.request().url()).origin === baseUrl.origin ? route.fallback() : route.abort());
await context.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
await context.route('https://fonts.gstatic.com/**', route => route.abort());
let firstRun = false;
const now = '2026-10-11T09:00:00Z';
const health = { startup_started_at: '2026-10-10T09:00:00Z', status: 'ok', version, timestamp: now, uptime_seconds: 86400,
    mqtt_connected: true, frigate_available: true, classifier_loaded: true,
    classifier: status, video_classifier: { pending: 0, active: 0 }, services: {} };
const workspace = { workspace_schema_version: '1', health, backend_diagnostics: { events: [], captured_at: now },
    focused_diagnostics: {}, classifier: status, startup_warnings: [], captured_at: now };
await context.route(url => url.origin === baseUrl.origin && (url.pathname === '/health' || url.pathname.startsWith('/api/')), async route => {
    const request = route.request(); const path = new URL(request.url()).pathname;
    if (path === '/api/auth/session-cookie') return route.fulfill({ json: { status: 'ok' } });
    if (path === '/api/auth/stream-ticket' && request.method() === 'POST') return route.fulfill({ json: { ticket: 'documentation-fixture-stream', expires_in_seconds: 60 } });
    if (request.method() !== 'GET') throw new Error(`Read-only screenshot fixture rejected ${request.method()} ${path}`);
    const json = payload => route.fulfill({ json: payload });
    if (path === '/api/sse') return route.fulfill({ contentType: 'text/event-stream', body: 'retry: 600000\n\n' });
    if (path === '/health') return json(health);
    if (path === '/api/version') return json({ version, base_version: version, branch: 'stable', git_hash: 'unknown' });
    if (path === '/api/auth/status') return json({ auth_required: true, public_access_enabled: false, is_authenticated: true, needs_initial_setup: firstRun, username: 'admin', show_camera_names: true, share_audio: true, share_photos: true });
    if (path === '/api/settings') return json(settings);
    if (path === '/api/garden/identification') return json({ country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [{ variant: '4.0.3a', installed: false, size_bytes: 223998782 }, { variant: '4.0.3b', installed: false, size_bytes: 223999179 }] });
    if (path === '/api/garden') return json({ items: [], total: 0, offset: 0, limit: 8 });
    if (path === '/api/classifier/status') return json(status);
    if (path === '/api/models/available') return json(catalog.available);
    if (path === '/api/models/installed') return json(catalog.installed);
    if (path === '/api/diagnostics/model-eval/runs') return json({ active: null, runs: [{ run_id: runId, status: 'completed', model_count: 1 }] });
    if (path === `/api/diagnostics/model-eval/runs/${runId}`) return json(compatibility);
    if (path.endsWith('/device_matrix.json')) return json(matrix);
    if (path.endsWith('.jpg')) {
        const photo = path.includes('robin') ? 'robin' : 'dunnock';
        return route.fulfill({ contentType: 'image/jpeg', body: await readFile(`${images}/fixtures/feeder-${photo}.jpg`) });
    }
    if (path === '/api/stats/daily-summary') return json({ total_count: 4, visit_count: 2, counted_birds: 0, counted_captures: 0, audio_confirmations: 0, camera_visits: [{ camera: 'feeder', visits: 2, last_seen: records[0].detection_time }], hourly_distribution: Array.from({ length: 24 }, (_,hour) => hour === 9 ? 3 : hour === 8 ? 1 : 0), hourly_visits: Array.from({ length: 24 }, (_,hour) => hour === 9 || hour === 8 ? 1 : 0), latest_detection: records[0], top_species: records.map((r,i) => ({ species: r.scientific_name, scientific_name: r.scientific_name, common_name: r.common_name, count: i ? 1 : 3, visit_count: 1, latest_event: r.frigate_event })) });
    if (path === '/api/audio/summary') return json(audioSummary);
    if (path === '/api/audio/history') return json({ total: 3, limit: 25, offset: 0, items: [0,1,2].map(i => ({ id: i+1, birdnet_id: null, species: 'European Robin', scientific_name: 'Erithacus rubecula', confidence: 0.93, timestamp: `2026-10-11T07:3${i*2}:00Z`, source_name: 'Garden microphone', sensor_id: 'garden', is_hidden: false })) });
    if (path === '/api/audio/recent') return json([]);
    if (path === '/api/audio/species') return json({ span: 'month', window_start: '2026-10-01T00:00:00Z', window_end: now, species: [{ species: 'European Robin', scientific_name: 'Erithacus rubecula', heard_count: 3, heard_prev_count: 0, heard_delta: 3, heard_percent: 0, avg_confidence: 0.93, last_heard: '2026-10-11T07:34:00Z' }] });
    if (path === '/api/leaderboard/species') return json({ span: 'month', species: speciesRows, window_start: '2026-10-01T00:00:00Z', window_end: now, previous_window_complete: false });
    if (path === '/api/leaderboard/portraits') return json({ span: 'month', portraits: records.map(r => ({ species: r.scientific_name, scientific_name: r.scientific_name, frigate_event: r.frigate_event, image_url: `/api/frigate/${r.frigate_event}/snapshot.jpg` })) });
    if (path === '/api/stats/detections/timeline') return json({ span: 'month', bucket: 'day', points: Array.from({ length: 6 }, (_,i) => ({ bucket_start: `2026-10-${String(6+i).padStart(2,'0')}T00:00:00Z`, label: `${6+i} Oct`, count: 2, unique_species: 2 })), total_count: 12, window_start: '2026-10-01T00:00:00Z', window_end: now, compare_series: [], weather: [] });
    if (path === '/api/stats/detections/activity-heatmap') return json({ span: 'month', window_start: '2026-10-01T00:00:00Z', window_end: now, total_count: 12, max_cell_count: 1, cells: Array.from({ length: 12 }, (_,i) => ({ day_of_week: 1 + Math.floor(i/2), hour: i % 2 ? 9 : 8, count: 1 })) });
    if (path === '/api/leaderboard/analysis') return route.fulfill({ status: 204 });
    if (path.includes('/species/') && path.endsWith('/info')) return json({ scientific_name: path.includes('Prunella') ? 'Prunella modularis' : 'Erithacus rubecula', common_name: path.includes('Prunella') ? 'Dunnock' : 'European Robin', thumbnail_url: null });
    if (path === '/api/species/search') return json(records.map(r => ({ id: r.scientific_name, display_name: r.common_name, scientific_name: r.scientific_name, common_name: r.common_name })));
    if (path.includes('/new-species')) return json({ items: [], total: 0 });
    if (path === '/api/ebird/notable-nearby') return json({ species: [], available: false, reason: 'not_configured' });
    if (path.endsWith('/snapshot/status')) return json({ available: true, source: 'frigate_snapshot_cropped', high_quality_bird_crop_enabled: true });
    if (path.endsWith('/snapshot/candidates')) return json({ event_id: 'dunnock', current_source: 'frigate_snapshot_cropped', current_candidate_id: 'dunnock__saved', candidates: [{ candidate_id: 'dunnock__saved', source_mode: 'retained_photo', clip_variant: 'retained_snapshot', frame_index: 0, ranking_score: 0, selected: true, image_url: '/api/frigate/dunnock/snapshot.jpg', thumbnail_url: '/api/frigate/dunnock/thumbnail.jpg' }], birds: [] });
    if (path === '/api/events') return json(new URL(request.url()).searchParams.get('limit') === '400' ? monthRecords : records);
    if (path === '/api/visits') return json({ total: visits.length, gap_seconds: 60, visits });
    if (/\/visits\/.+\/captures$/.test(path)) return json({ total: 3, captures: [0,1,2].map(i => ({ ...records[0], frigate_event: i ? `doc-dunnock-${i}` : 'doc-dunnock', detection_time: new Date(Date.parse(records[0].detection_time) + i * 11_000).toISOString() })) });
    if (path === '/api/audio/heard-groups') return json({ call_count: 3, gap_seconds: 60, correlation_window_seconds: 60, truncated: false, matched_visits: [], groups: [{ species: 'European Robin', scientific_name: 'Erithacus rubecula', source_name: 'Garden microphone', call_count: 3, first_heard: '2026-10-11T07:30:00Z', last_heard: '2026-10-11T07:34:00Z', best_heard: '2026-10-11T07:32:00Z', best_confidence: 0.93, best_birdnet_id: null }] });
    if (path === '/api/events/count') return json({ count: records.length });
    if (path === '/api/events/hidden-count') return json({ hidden_count: 0 });
    if (path.startsWith('/api/audio/context/') || path.includes('/conversation')) return json([]);
    if (path === '/api/setup/state') return json({ initial_setup_complete: !firstRun, sections: [
        { id: 'account', status: 'ok', detail_code: 'account_password_protected' },
        { id: 'connection', status: 'ok', detail_code: 'connection_ready', detail_values: { url: settings.frigate_url } },
        { id: 'cameras', status: 'ok', detail_code: 'cameras_count', detail_values: { count: 1 } },
        { id: 'model', status: 'ok', detail_code: 'model_selected', detail_values: { model: 'DINOv2 B/14 with location' } },
        { id: 'quality', status: 'optional', detail_code: 'quality_best' },
        { id: 'integrations', status: 'optional', detail_code: 'integrations_none' },
    ] });
    if (path === '/api/diagnostics/workspace') return json(workspace);
    if (path.endsWith('/jobs')) return json({ items: [], captured_at: now });
    if (path.endsWith('/system-telemetry/history')) return json({ points: [], accelerators: [], processes: [], host: { memory_total_bytes: 8589934592, cpu_count: 4 }, window_seconds: 1800 });
    if (path.endsWith('/frigate/config')) return json({ cameras: { feeder: { record: { enabled: true } } } });
    if (path.endsWith('/backfill/status')) return json(null);
    if (path.endsWith('/audio/sources')) return json([]);
    if (path.endsWith('/labels')) return json({ labels: ['Prunella modularis', 'Erithacus rubecula'] });
    if (path.endsWith('/filters')) return json({ cameras: ['feeder'], species: records.map(r => ({ value: r.scientific_name, display_name: r.common_name, common_name: r.common_name, scientific_name: r.scientific_name, count: 1 })), camera_counts: { feeder: 2 }, totals: { total: 2, favorites: 0, audio_matched: 0 } });
    if (path.endsWith('/detections') || path.endsWith('/species') || path.endsWith('/events')) return json([]);
    if (path.endsWith('/cache/stats')) return json({ storage_available: true, total_size_mb: 326, snapshot_count: 120, clip_count: 40, favorite_archive: { captures: 8, completed: 8, failed: 0, pending: 0, size_mb: 38 } });
    return json({});
});
const page = await context.newPage();
await page.clock.install({ time: new Date(now) });
page.on('pageerror', error => errors.push(error.message));
async function shot(name, locator) {
    await locator.waitFor({ state: 'visible' });
    await page.evaluate(() => document.fonts.ready);
    await locator.screenshot({ path: `${images}/${name}.png`, animations: 'disabled' });
    captured.push(name); console.log(`Captured ${name}`);
}
async function openSettings(tab) {
    await page.goto(`${base}/browser-tests/settings-backfill.html`);
    await page.getByRole('link', { name: tab, exact: true }).click();
    await page.waitForTimeout(350);
}
await mkdir(images, { recursive: true });
try {
    if (gardenOnly) {
        await openSettings('Beta features');
        await shot('settings-garden-cameras', page.locator('[data-garden-beta-settings]'));
        await page.goto(`${base}/browser-tests/garden.html`);
        await page.getByText('No captures in this view').waitFor();
        await page.getByText('Species suggestions', { exact: true }).click();
        await page.getByText('Country filter: GBR', { exact: true }).waitFor();
        await shot('garden-review', page.locator('#app'));
    } else {
    await openSettings('Connection');
    await shot('settings-map', page.locator('[data-settings-navigation]'));
    for (const [tab, name] of [['Connection','settings-connection'],['Detection','settings-detection'],['Integrations','settings-integrations'],['Notifications','settings-notifications'],['Security','settings-security'],['Data','settings-data']]) {
        await openSettings(tab);
        const content = page.locator('main > div > div.space-y-6').last();
        if (await content.count()) {
            const box = await content.boundingBox();
            await page.screenshot({ path: `${images}/${name}.png`, clip: { x: box.x, y: box.y, width: box.width, height: Math.min(box.height, 850) }, animations: 'disabled' });
            captured.push(name); console.log(`Captured ${name}`);
        }
    }
    await openSettings('Detection');
    const selectedModel = page.locator('section[aria-labelledby="selected-model-name"]');
    await selectedModel.evaluate(el => el.scrollIntoView({ block: 'center' }));
    await page.waitForTimeout(100);
    const modelBox = await selectedModel.boundingBox();
    await page.screenshot({ path: `${images}/model-manager-dino.png`, clip: { x: Math.max(0,modelBox.x-12), y: Math.max(0,modelBox.y-12), width: modelBox.width+24, height: modelBox.height+24 }, animations: 'disabled' });
    captured.push('model-manager-dino');
    await page.setViewportSize({ width: 760, height: 1600 });
    await page.goto(`${base}/browser-tests/media-settings.html`);
    await shot('settings-media-retention', page.locator('section').filter({ has: page.getByRole('heading', { name: 'Photos and video', exact: true }) }));
    await page.setViewportSize({ width: 1280, height: 960 });
    await page.goto(`${base}/browser-tests/model-eval.html`);
    await page.getByText('Compatibility check only', { exact: true }).waitFor();
    await shot('model-evaluation-compatibility', page.locator('#app > div').first());
    await page.goto(`${base}/browser-tests/support.html`);
    await page.getByRole('button', { name: /Health.*Diagnostics export/ }).click();
    await page.locator('[data-health-timeline] ol > li').first().waitFor();
    await shot('settings-health', page.locator('#app > main > div.space-y-6').first());
    const support = page.locator('[data-diagnostics-export]');
    await support.locator('summary').click();
    await support.getByRole('textbox', { name: 'What went wrong? Included in the bundle.' }).fill('Classification paused after a network change. Please review the fresh diagnostics.');
    await shot('support-bundle', support);
    firstRun = true;
    await page.goto(`${base}/browser-tests/setup-wizard.html`);
    await shot('setup-wizard', page.getByRole('dialog'));
    await page.getByRole('button', { name: 'Get started', exact: true }).click();
    await shot('setup-wizard-account', page.getByRole('dialog'));
    firstRun = false;
    await page.goto(`${base}/browser-tests/setup-wizard.html`);
    await page.getByRole('button', { name: 'Open setup wizard', exact: true }).click();
    await page.getByRole('listitem').filter({ hasText: 'Classifier model & hardware' }).getByRole('button', { name: 'Review', exact: true }).click();
    await page.getByText('Feeder location', { exact: true }).waitFor();
    await shot('setup-wizard-dino', page.getByRole('dialog'));
    await page.setViewportSize({ width: 1280, height: 960 });
    await page.goto(`${base}/browser-tests/owner-history.html?surface=explorer&theme=dark`);
    await page.locator('[data-explorer-visit="doc-dunnock"]').waitFor();
    await page.evaluate(async () => {
        const { settingsStore } = await import('/src/lib/stores/settings.svelte.ts');
        settingsStore.settings = { ...settingsStore.settings, birdnet_enabled: true };
    });
    await page.locator('[data-explorer-heard-toggle]').click();
    await page.locator('[data-heard-band-card]').waitFor();
    await shot('explorer', page.locator('#app > div').last());
    await shot('explorer-heard-calls', page.locator('[data-heard-band-card]'));
    await page.locator('[data-explorer-visit="doc-dunnock"] [data-visit-captures-toggle]').click();
    await page.locator('[data-visit-capture]').first().waitFor();
    await shot('explorer-captures', page.locator('[data-visit-captures-floating]'));
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto(`${base}/browser-tests/documentation.html`);
    await page.locator('[data-field-log-visit="doc-dunnock"]').waitFor();
    await shot('dashboard-field-log', page.locator('[data-field-log-visit="doc-dunnock"]'));
    // Overview figures include the real app shell, not only the Dashboard page.
    await page.goto(base);
    await page.locator('[data-field-log-visit="doc-dunnock"]').waitFor();
    const sidebar = page.locator('aside').filter({ has: page.locator('nav') });
    await sidebar.getByRole('button', { name: 'Explorer', exact: true }).waitFor();
    await sidebar.locator('[data-sidebar-account]').waitFor();
    const sidebarBox = await sidebar.boundingBox();
    if (!sidebarBox || sidebarBox.x < 0 || sidebarBox.y < 0
        || sidebarBox.width < 200 || sidebarBox.x + sidebarBox.width > 1920
        || sidebarBox.y + sidebarBox.height > 1080) {
        throw new Error('Dashboard overview must include the complete expanded sidebar');
    }
    await shot('dashboard', page.locator('body'));
    await page.setViewportSize({ width: 390, height: 1000 });
    await page.getByRole('button', { name: 'Toggle menu', exact: true }).waitFor();
    await page.screenshot({ path: `${images}/dashboard-mobile.png`, animations: 'disabled' });
    captured.push('dashboard-mobile');
    await page.setViewportSize({ width: 1280, height: 960 });
    await page.goto(`${base}/browser-tests/documentation.html?surface=manual`);
    await shot('add-observation', page.locator('#app'));
    await page.goto(`${base}/browser-tests/species-charts.html`);
    await page.getByText('Dunnock', { exact: true }).first().waitFor();
    await page.waitForTimeout(500);
    await shot('leaderboard', page.locator('#app'));
    await page.goto(`${base}/browser-tests/audio-charts.html`);
    await page.locator('[data-audio-history-analytics]').waitFor();
    await page.waitForTimeout(500);
    await shot('audio-history', page.locator('#app'));
    await page.goto(`${base}/browser-tests/review-media.html?surface=record&queue=dunnock&theme=dark`);
    await page.getByRole('dialog').waitFor();
    await page.waitForTimeout(500);
    await shot('detection-detail', page.getByRole('dialog'));
    await page.goto(`${base}/browser-tests/review-media.html?surface=queue&queue=dunnock&theme=dark`);
    await page.getByRole('dialog').waitFor();
    await page.waitForTimeout(500);
    await page.getByRole('button', { name: /European Robin.*Identify/ }).waitFor();
    await shot('detection-photo-review', page.getByRole('dialog'));
    }
    if (errors.length) throw new Error(`Browser errors: ${errors.join('; ')}`);
    console.log(JSON.stringify({ captured, pageErrors: errors }, null, 2));
} finally { await browser.close(); }
