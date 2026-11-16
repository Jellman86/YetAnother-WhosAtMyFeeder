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
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toContainText('The MQTT broker at mqtt.invalid:1883 is not connected, so no new detections can arrive.');
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toContainText('Check its address in Settings → Connection and that the broker is running.');
    await expect(status.locator('[data-health-problem="frigate_down"]')).toContainText('Frigate at http://frigate.invalid:5000 is not answering');
    await expect(status).not.toContainText('Settings, Connection');
    await expect(page.getByText('All monitored services look healthy right now.')).toHaveCount(0);
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
