import { expect, test, type Page } from '@playwright/test';
import { replayFeeder } from './accessibility-mock';

/**
 * Leaving a page cancels the read it was waiting on, body included. The page's fetch is wrapped
 * so that one path answers with headers and then a body that never ends; each such read records
 * whether it was aborted, and why, so a read freed only by its own timeout does not pass.
 */
interface StalledRead {
    path: string;
    aborted: boolean;
    reason: string;
}

async function stallBodies(page: Page, path: string): Promise<void> {
    await page.addInitScript((stalledPath) => {
        const reads: StalledRead[] = [];
        (window as unknown as { __stalledReads: StalledRead[] }).__stalledReads = reads;
        const realFetch = window.fetch.bind(window);
        window.fetch = (input: RequestInfo | URL, init?: RequestInit) => {
            const url = new URL(input instanceof Request ? input.url : String(input), location.href);
            if (url.pathname !== stalledPath) return realFetch(input, init);
            const read: StalledRead = { path: url.pathname, aborted: false, reason: '' };
            reads.push(read);
            const signal = init?.signal ?? undefined;
            const body = new ReadableStream<Uint8Array>({
                start(controller) {
                    controller.enqueue(new TextEncoder().encode('{"partial": '));
                    signal?.addEventListener('abort', () => {
                        read.aborted = true;
                        read.reason = String((signal.reason as { message?: unknown } | undefined)?.message ?? signal.reason);
                        controller.error(new DOMException('The operation was aborted.', 'AbortError'));
                    });
                }
            });
            return Promise.resolve(new Response(body, { status: 200, headers: { 'Content-Type': 'application/json' } }));
        };
    }, path);
}

function stalledReads(page: Page): Promise<StalledRead[]> {
    return page.evaluate(() => (window as unknown as { __stalledReads: StalledRead[] }).__stalledReads);
}

/** A cancel is the reader's own abort; a timeout would say it timed out, and is too late here. */
async function expectCancelledOnLeaving(page: Page, leave: () => Promise<void>): Promise<void> {
    await expect.poll(async () => (await stalledReads(page)).length, { timeout: 15_000 }).toBeGreaterThan(0);
    expect((await stalledReads(page)).every((read) => !read.aborted)).toBe(true);
    await leave();
    // Well inside both reads' own timeouts (15 s and 10 s), so only the cancel can have ended them.
    await expect.poll(async () => (await stalledReads(page)).every((read) => read.aborted), { timeout: 3_000 }).toBe(true);
    for (const read of await stalledReads(page)) expect(read.reason).not.toMatch(/timed out/i);
}

const HEALTH_WORKSPACE = {
    workspace_schema_version: 'fixture',
    backend_diagnostics: {
        captured_at: new Date().toISOString(),
        capacity: 500,
        total_events: 0,
        total_occurrences: 0,
        filtered_events: 0,
        returned_events: 0,
        severity_counts: {},
        component_counts: {},
        events: []
    },
    focused_diagnostics: {},
    // A start time is what makes Health read the visits since it.
    health: { status: 'healthy', startup_started_at: new Date(Date.now() - 3_600_000).toISOString() },
    connections: null,
    classifier: {},
    taxonomy_repair: {},
    maintenance_coordinator: {},
    startup_warnings: []
};

test("leaving Health cancels its visits read while the body is still arriving", async ({ page }) => {
    await stallBodies(page, '/api/visits');
    await replayFeeder(page, 'light', { '/api/diagnostics/workspace': HEALTH_WORKSPACE });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/system-health');
    await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible({ timeout: 15_000 });
    await expectCancelledOnLeaving(page, () => page.locator('#app-sidebar').getByRole('button', { name: 'Settings', exact: true }).click());
});

test('leaving Settings › Models cancels its runtime read while the body is still arriving', async ({ page }) => {
    await stallBodies(page, '/api/classifier/status');
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/settings/models');
    await expectCancelledOnLeaving(page, () => page.locator('[data-settings-navigation]').getByRole('link', { name: 'Appearance' }).click());
});
