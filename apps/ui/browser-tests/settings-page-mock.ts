import { expect, type Page } from '@playwright/test';

// The whole Settings page on fixture data, for tests of tab drafts and Apply. GET /api/settings
// returns `saved` over a minimal connection, every POST is recorded and merged into what the next
// GET returns, and endpoints a tab does not need answer with an empty body.

export type FixtureSettings = Record<string, unknown>;

export interface SettingsHarness {
    writes: FixtureSettings[];
    /** How many times the browser fetched a module whose path ends with `fileName`. */
    moduleRequests: (fileName: string) => number;
}

export async function openSettings(page: Page, saved: FixtureSettings = {}): Promise<SettingsHarness> {
    let settings: FixtureSettings = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
        cameras: [], classification_threshold: 0.7, trusted_proxy_hosts: ['*'], notifications_notify_on_insert: true,
        ...saved
    };
    const writes: FixtureSettings[] = [];
    const requestedPaths: string[] = [];
    page.on('request', request => requestedPaths.push(new URL(request.url()).pathname));
    await page.route(url => url.pathname.startsWith('/api/') || url.pathname === '/health', async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload = request.postDataJSON() as FixtureSettings;
                writes.push(payload);
                settings = { ...settings, ...payload };
                return route.fulfill({ json: { status: 'updated' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path === '/api/models/installed' || path === '/api/models/available') return route.fulfill({ json: [] });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    return {
        writes,
        moduleRequests: fileName => requestedPaths.filter(path => path.endsWith(`/${fileName}`)).length
    };
}

export const unsavedChanges = (page: Page) => page.getByText('Unsaved Changes', { exact: true });
