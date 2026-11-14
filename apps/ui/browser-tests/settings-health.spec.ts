import { expect, test } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// Settings → Health is the diagnostics page shown as a tab. It loads only when opened, and a
// detection set aside elsewhere in Settings links straight to it.

test('Health loads on first open and keeps the form untouched', async ({ page }) => {
    const harness = await openSettings(page);
    expect(harness.moduleRequests('Errors.svelte')).toBe(0);

    await page.getByRole('link', { name: 'Health' }).click();
    await expect(page.locator('[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/settings/health');
    await expect(page.locator('[data-health-timeline]')).toBeVisible();
    expect(harness.moduleRequests('Errors.svelte')).toBe(1);
    await expect(page.getByText('Unsaved Changes', { exact: true })).toHaveCount(0);

    await page.getByRole('link', { name: 'Connection' }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await page.getByRole('link', { name: 'Health' }).click();
    await expect(page.locator('[data-health-timeline]')).toBeVisible();
    expect(harness.moduleRequests('Errors.svelte')).toBe(1);
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

test('Health never reads healthy while the broker and Frigate are down', async ({ page }) => {
    await openSettings(page);
    await page.route(url => url.pathname === '/api/diagnostics/workspace', route => route.fulfill({ json: workspace({
        mqtt: { state: 'disconnected', server: 'mqtt.invalid', port: 1883, last_attempt_at: '2026-11-13T18:18:00Z', last_error: '[Errno -2] Name or service not known' },
        frigate: { state: 'unreachable', url: 'http://frigate.invalid:5000', checked_at: '2026-11-13T18:19:00Z', last_failure: 'connection', availability: 'unknown' },
        generated_at: '2026-11-13T18:20:00Z'
    }) }));
    await page.getByRole('link', { name: 'Health' }).click();

    const status = page.locator('[data-health-status]');
    await expect(status.locator('[data-health-status-pill]')).toHaveText('Degraded');
    // One short item per failed connection, each with what to do, in the app's own path style.
    const problems = status.locator('[data-health-problem]');
    await expect(problems).toHaveCount(2);
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toContainText('The MQTT broker at mqtt.invalid:1883 is not connected, so no new detections can arrive.');
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toContainText('Check its address in Settings → Connection and that the broker is running.');
    await expect(status.locator('[data-health-problem="frigate_down"]')).toContainText('Frigate at http://frigate.invalid:5000 is not answering');
    await expect(status).not.toContainText('Settings, Connection');
    await expect(page.getByText('All monitored services look healthy right now.')).toHaveCount(0);

    await page.locator('[data-subsystem-detail] summary').click();
    const mqtt = page.locator('[data-health-card="mqtt"]');
    await expect(mqtt).toHaveAttribute('data-health-card-status', 'disconnected');
    await expect(mqtt).toContainText('Not connected');
    await expect(mqtt).toContainText('Not connected to mqtt.invalid:1883.');
    await expect(mqtt).toContainText('Name or service not known');
    await expect(mqtt).not.toContainText('flowing normally');
    const frigate = page.locator('[data-health-card="frigate"]');
    await expect(frigate).toHaveAttribute('data-health-card-status', 'unreachable');
    await expect(frigate).toContainText('the address could not be reached');
});

test('Health is healthy only with both connections measured up', async ({ page }) => {
    await openSettings(page);
    await page.route(url => url.pathname === '/api/diagnostics/workspace', route => route.fulfill({ json: workspace({
        mqtt: { state: 'connected', server: 'mqtt', port: 1883, connected_since: '2026-11-13T17:00:00Z' },
        frigate: { state: 'reachable', url: 'http://frigate:5000', checked_at: '2026-11-13T18:19:00Z', availability: 'online' },
        generated_at: '2026-11-13T18:20:00Z'
    }) }));
    await page.getByRole('link', { name: 'Health' }).click();
    await expect(page.locator('[data-health-status-pill]')).toHaveText('Healthy');
    await page.locator('[data-subsystem-detail] summary').click();
    await expect(page.locator('[data-health-card="mqtt"]')).toContainText('Connected to mqtt:1883 since');
    await expect(page.locator('[data-health-card="frigate"]')).toContainText('Frigate announces itself online over MQTT.');
});
