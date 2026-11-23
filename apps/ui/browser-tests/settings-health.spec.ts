import { expect, test, type Page } from '@playwright/test';
import { replayFeeder } from './accessibility-mock';

// Health is a page of its own under Manage, at /system-health (the backend answers /health). Its
// verdict and its list of open problems come from one reading, so the two always agree.

async function openHealth(page: Page, workspacePayload: unknown): Promise<void> {
    await replayFeeder(page, 'light', { '/api/diagnostics/workspace': workspacePayload });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/system-health');
    await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible({ timeout: 15_000 });
}

test('Health is a page under Manage, reached from the sidebar and from its old Settings address', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/settings/health');
    await expect.poll(() => new URL(page.url()).pathname).toBe('/system-health');
    await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-health-timeline]')).toBeVisible();
    await expect(page.locator('[data-settings-navigation]')).toHaveCount(0);
    await page.locator('#app-sidebar').getByRole('button', { name: 'Settings', exact: true }).click();
    await expect(page.locator('[data-settings-navigation]').getByRole('link', { name: 'Health' })).toHaveCount(0);
    await page.locator('#app-sidebar').getByRole('button', { name: 'Health', exact: true }).click();
    await expect.poll(() => new URL(page.url()).pathname).toBe('/system-health');
});


function workspace(connections: Record<string, unknown>) {
    return {
        workspace_schema_version: 'test',
        backend_diagnostics: { captured_at: '2026-11-13T18:20:00Z', events: [] },
        focused_diagnostics: {},
        // Everything inside the app reports fine; only the connections are down.
        health: { status: 'ok', mqtt: { pressure_level: 'normal', in_flight: 0, in_flight_capacity: 200 }, event_pipeline: { status: 'ok' } },
        connections,
        classifier: {},
        taxonomy_repair: {},
        maintenance_coordinator: {},
        startup_warnings: []
    };
}

test('Health never reads healthy while the broker and Frigate are down, and lists them as the open problems', async ({ page }) => {
    await openHealth(page, workspace({
        mqtt: { state: 'disconnected', server: 'mqtt.invalid', port: 1883, last_attempt_at: '2026-11-13T18:18:00Z', last_error: '[Errno -2] Name or service not known', last_error_cause: 'host_not_found' },
        frigate: { state: 'unreachable', url: 'http://frigate.invalid:5000', checked_at: '2026-11-13T18:19:00Z', last_failure: 'connection', availability: 'unknown' },
        generated_at: '2026-11-13T18:20:00Z'
    }));

    const status = page.locator('[data-health-status]');
    await expect(status.locator('[data-health-status-pill]')).toHaveText('Degraded');
    // One short item per failed connection, each with what to do, in the app's own path style.
    const problems = status.locator('[data-health-problem]');
    await expect(problems).toHaveCount(2);
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toContainText('The MQTT broker at mqtt.invalid:1883 is not connected, so no new visits can be recorded.');
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toContainText('Check its address in Settings → Cameras & connection and that the broker is running.');
    await expect(status.locator('[data-health-problem="frigate_down"]')).toContainText('Frigate at http://frigate.invalid:5000 is not answering');
    await expect(status).not.toContainText('Settings, Connection');
    await expect(page.getByText('Everything YA-WAMF checks is working.')).toHaveCount(0);
    // Nothing below contradicts the verdict: the panel holds only incidents that have cleared.
    await expect(page.locator('main')).not.toContainText('0 open');
    await expect(page.locator('[data-health-earlier-incidents]')).toContainText('Earlier incidents');
    await expect(page.getByRole('button', { name: 'Clear error history' })).toBeVisible();

    await page.locator('[data-subsystem-detail] > summary').click();
    const mqtt = page.locator('[data-health-card="mqtt"]');
    await expect(mqtt).toHaveAttribute('data-health-card-status', 'disconnected');
    await expect(mqtt).toContainText('Not connected');
    await expect(mqtt).toContainText('Not connected to mqtt.invalid:1883.');
    // The cause is worded from its code; the resolver's errno text is only a technical detail.
    await expect(mqtt.locator('[data-health-mqtt-cause]')).toHaveText('MQTT broker: the host name in mqtt.invalid:1883 was not found. Check the address.');
    await expect(mqtt.locator('[data-health-mqtt-cause]')).not.toContainText('Errno');
    await expect(mqtt).toContainText('Name or service not known');
    await expect(mqtt).not.toContainText('flowing normally');
    const frigate = page.locator('[data-health-card="frigate"]');
    await expect(frigate).toHaveAttribute('data-health-card-status', 'unreachable');
    await expect(frigate).toContainText('the address could not be reached');
});

test('Health is healthy only with both connections measured up', async ({ page }) => {
    await openHealth(page, workspace({
        mqtt: { state: 'connected', server: 'mqtt', port: 1883, connected_since: '2026-11-13T17:00:00Z' },
        frigate: { state: 'reachable', url: 'http://frigate:5000', checked_at: '2026-11-13T18:19:00Z', availability: 'online' },
        generated_at: '2026-11-13T18:20:00Z'
    }));
    await expect(page.locator('[data-health-status-pill]')).toHaveText('Healthy');
    await page.locator('[data-subsystem-detail] > summary').click();
    await expect(page.locator('[data-health-card="mqtt"]')).toContainText('Connected to mqtt:1883 since');
    await expect(page.locator('[data-health-card="frigate"]')).toContainText('Frigate announces itself online over MQTT.');
});

test('a backend error is said in words; its raw text, paths and addresses stay under Technical details', async ({ page }) => {
    const event = (reason: string, message: string) => ({
        id: `diag:test:${reason}`, timestamp: '2026-11-13T18:19:00Z', source: 'event_pipeline', component: 'event_processor',
        stage: 'classify', reason_code: reason, message, severity: 'critical', event_id: 'evt-1', context: null,
        correlation_key: null, count: 1, first_seen: '2026-11-13T18:19:00Z', last_seen: '2026-11-13T18:19:00Z'
    });
    const payload = workspace({
        mqtt: { state: 'connected', server: 'mqtt', port: 1883, connected_since: '2026-11-13T17:00:00Z' },
        frigate: { state: 'reachable', url: 'http://frigate:5000', checked_at: '2026-11-13T18:19:00Z', availability: 'online' },
        generated_at: '2026-11-13T18:20:00Z'
    });
    payload.backend_diagnostics.events = [
        event('stage_failure', "Stage classify failed: [Errno 2] No such file or directory: '/data/models/bird.onnx' via http://frigate:5000/api"),
        event('something_new', 'Unrecognised failure at /config/secret-path')
    ] as never[];
    await openHealth(page, payload);

    const rows = page.locator('[data-health-diagnostic]');
    await expect(rows).toHaveCount(2);
    await expect(rows.nth(0).locator('[data-health-diagnostic-title]')).toHaveText('A Frigate event could not be processed because one of its steps failed.');
    await expect(rows.nth(1).locator('[data-health-diagnostic-title]')).toHaveText('A processing step failed in a way YA-WAMF does not recognise.');
    // An unknown failure still ends in something to do, without pretending to know the cause.
    await expect(rows.nth(1)).toContainText('YA-WAMF cannot say what caused it; the exact error is under Technical details. If it happens again, capture a diagnostics bundle below and report it.');
    // Nothing raw is on screen until Technical details is opened; the whole page is checked, verdict included.
    const visible = await page.locator('main').innerText();
    for (const raw of ['/data/models', 'http://frigate:5000/api', '/config/secret-path', 'Errno']) expect(visible).not.toContain(raw);
    await rows.nth(0).locator('summary').click();
    await expect(rows.nth(0)).toContainText("'/data/models/bird.onnx'");
});

test('on a phone, System status puts its pill in the header row so open incidents use the full card width and show count and camera', async ({ page }) => {
    const payload = workspace({
        mqtt: { state: 'connected', server: 'mqtt', port: 1883, connected_since: '2026-11-13T17:00:00Z' },
        frigate: { state: 'reachable', url: 'http://frigate:5000', checked_at: '2026-11-13T18:19:00Z', availability: 'online' },
        generated_at: '2026-11-13T18:20:00Z'
    });
    payload.backend_diagnostics.events = [
        {
            id: 'diag:test:snapshot-unavailable',
            timestamp: '2026-11-13T18:19:00Z',
            source: 'event_pipeline',
            component: 'event_processor',
            stage: 'classify_snapshot',
            reason_code: 'drop_classify_snapshot_unavailable',
            message: 'Dropped event due to classify_snapshot_unavailable',
            severity: 'error',
            event_id: 'evt-snap-1',
            context: { camera: 'birdcam' },
            correlation_key: null,
            count: 3,
            first_seen: '2026-11-13T18:05:00Z',
            last_seen: '2026-11-13T18:19:00Z'
        }
    ] as never[];

    await replayFeeder(page, 'dark', { '/api/diagnostics/workspace': payload });
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto('/system-health');
    await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible({ timeout: 15_000 });

    const statusCard = page.locator('[data-health-status] > div').first();
    const incident = page.locator('[data-health-open-incident]').first();
    await expect(incident).toBeVisible();
    await expect(incident.locator('[data-health-incident-meta]')).toContainText('Happened 3 times');
    await expect(incident.locator('[data-health-incident-meta]')).toContainText('birdcam');

    const cardBox = await statusCard.boundingBox();
    const incidentBox = await incident.boundingBox();
    expect(cardBox && incidentBox).toBeTruthy();
    // Open incidents span the full inner width of the card rather than sitting beside the verdict pill.
    expect(incidentBox!.width).toBeGreaterThan(cardBox!.width - 48);
});
