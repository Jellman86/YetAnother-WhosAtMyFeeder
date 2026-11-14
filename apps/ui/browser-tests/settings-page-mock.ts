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

export interface SettingsHarnessOptions {
    /** Answers a request the harness would otherwise answer with an empty body; undefined passes. */
    respond?: (path: string, method: string) => { status?: number; json: unknown } | undefined;
    /** Answers a settings write instead of accepting it, e.g. to refuse it; undefined accepts it. */
    refuseWrite?: (payload: FixtureSettings) => { status: number; json: unknown } | undefined;
}

export async function openSettings(page: Page, saved: FixtureSettings = {}, options: SettingsHarnessOptions = {}): Promise<SettingsHarness> {
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
                const refusal = options.refuseWrite?.(payload);
                if (refusal) return route.fulfill(refusal);
                settings = { ...settings, ...payload };
                return route.fulfill({ json: { status: 'updated' } });
            }
            return route.fulfill({ json: settings });
        }
        const answer = options.respond?.(path, request.method());
        if (answer) return route.fulfill(answer);
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

/** The save bar, present only while the draft differs from what is saved. */
export const saveBar = (page: Page) => page.getByRole('region', { name: 'Unsaved changes' });
export const saveButton = (page: Page) => saveBar(page).getByRole('button', { name: 'Save changes', exact: true });
export const discardButton = (page: Page) => saveBar(page).getByRole('button', { name: 'Discard changes', exact: true });
