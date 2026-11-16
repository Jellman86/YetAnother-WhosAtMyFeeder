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

type HarnessAnswer = { status?: number; json: unknown };

export interface SettingsHarnessOptions {
    /**
     * Answers a request the harness would otherwise answer with an empty body; undefined passes.
     * A promise holds the answer until it settles, as a slow upstream does.
     */
    respond?: (path: string, method: string) => HarnessAnswer | undefined | Promise<HarnessAnswer | undefined>;
    /** Answers a settings write instead of accepting it, e.g. to refuse it; undefined accepts it. */
    refuseWrite?: (payload: FixtureSettings) => { status: number; json: unknown } | undefined;
    /** The tab to open on, as its route; Connection when omitted. */
    route?: string;
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
        const answer = await options.respond?.(path, request.method());
        // A held answer can outlive the request: the page may have cancelled it meanwhile.
        if (answer) return route.fulfill(answer).catch(() => undefined);
        if (path === '/api/models/installed' || path === '/api/models/available') return route.fulfill({ json: [] });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto(`/browser-tests/settings-backfill.html${options.route ? `?route=${encodeURIComponent(options.route)}` : ''}`);
    // The first open compiles the page and its tab on the dev server, which is slow under load.
    if (options.route) await expect(page.locator('[data-settings-navigation]')).toBeVisible({ timeout: 15_000 });
    else await expect(page.locator('#mqtt-server')).toHaveValue('mqtt', { timeout: 15_000 });
    return {
        writes,
        moduleRequests: fileName => requestedPaths.filter(path => path.endsWith(`/${fileName}`)).length
    };
}

/** The save bar, present only while the draft differs from what is saved. */
export const saveBar = (page: Page) => page.getByRole('region', { name: 'Unsaved changes' });
export const saveButton = (page: Page) => saveBar(page).getByRole('button', { name: 'Save changes', exact: true });
export const discardButton = (page: Page) => saveBar(page).getByRole('button', { name: 'Discard changes', exact: true });
