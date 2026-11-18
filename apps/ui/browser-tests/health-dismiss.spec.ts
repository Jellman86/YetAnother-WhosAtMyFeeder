import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';

// Dismiss hides a recorded warning for everyone on this install; Show dismissed and Restore bring
// it back, and nothing is deleted. The server keeps the dismissals, so the fixture plays its part.

interface FixtureEntry {
    id: string;
    component: string;
    reason_code: string;
    message: string;
    last_seen: string;
    count?: number;
    /** How many occurrences the fixture server's dismissal covers, as the real one keeps it. */
    dismissedCount?: number;
}

const CONNECTED = {
    mqtt: { state: 'connected', server: 'mqtt', port: 1883, connected_since: '2026-11-18T07:00:00Z' },
    frigate: { state: 'reachable', url: 'http://frigate:5000', checked_at: '2026-11-18T07:59:00Z', availability: 'online' },
    generated_at: '2026-11-18T08:00:00Z'
};

function fixtureWorkspace(entries: FixtureEntry[], connections: unknown) {
    return {
        workspace_schema_version: 'test',
        backend_diagnostics: {
            captured_at: '2026-11-18T08:00:00Z',
            capacity: 500,
            total_events: entries.length,
            filtered_events: entries.length,
            returned_events: entries.length,
            severity_counts: { error: entries.length },
            component_counts: {},
            // The server's answer is rebuilt on every read, so a dismissal shows on the next one.
            get events() {
                return entries.map(({ dismissedCount, ...entry }) => ({
                    ...entry,
                    source: 'event_pipeline',
                    severity: 'error',
                    timestamp: entry.last_seen,
                    first_seen: entry.last_seen,
                    count: entry.count ?? 1,
                    // The server's rule: hidden while no occurrence beyond those dismissed has been recorded.
                    dismissed: dismissedCount !== undefined && (entry.count ?? 1) <= dismissedCount
                }));
            }
        },
        focused_diagnostics: {},
        health: { status: 'ok', mqtt: { pressure_level: 'normal', in_flight: 0, in_flight_capacity: 200 }, event_pipeline: { status: 'ok' } },
        connections,
        classifier: {},
        taxonomy_repair: {},
        maintenance_coordinator: {},
        startup_warnings: []
    };
}

interface OpenOptions {
    theme?: Theme;
    extra?: FixtureEntry[];
    connections?: unknown;
    /** Runs on the fixture server before it answers a dismissal: a new occurrence, a clear. */
    beforeDismiss?: (entries: FixtureEntry[]) => void;
}

async function openHealth(page: Page, options: OpenOptions = {}): Promise<{ entries: FixtureEntry[]; posts: string[] }> {
    const { theme = 'light', extra = [], connections = CONNECTED, beforeDismiss } = options;
    const entries: FixtureEntry[] = [
        ...extra,
        { id: 'diag:fixture:1', component: 'event_processor', reason_code: 'drop_classify_snapshot_timeout', message: 'Dropped event due to classify_snapshot_timeout', last_seen: '2026-11-18T07:40:00Z' },
        { id: 'diag:fixture:2', component: 'event_processor', reason_code: 'stage_failure', message: 'Stage save_and_notify failed', last_seen: '2026-11-18T07:30:00Z' }
    ];
    const posts: string[] = [];
    await replayFeeder(page, theme, { '/api/diagnostics/workspace': fixtureWorkspace(entries, connections) });
    // Registered after the replay, so these answer the two writes the replay refuses.
    await page.route((url) => url.pathname === '/api/diagnostics/dismissals', async (route) => {
        const body = route.request().postDataJSON() as { entries: { id: string; count: number }[] };
        posts.push(`dismiss ${body.entries.map((item) => `${item.id}×${item.count}`).join(',')}`);
        beforeDismiss?.(entries);
        const dismissed: unknown[] = [];
        const missing: string[] = [];
        for (const item of body.entries) {
            const entry = entries.find((candidate) => candidate.id === item.id);
            if (!entry) {
                missing.push(item.id);
                continue;
            }
            entry.dismissedCount = Math.min(item.count, entry.count ?? 1);
            dismissed.push({ id: entry.id, component: entry.component, reason_code: entry.reason_code, dismissed_count: entry.dismissedCount, dismissed_at: '2026-11-18T08:01:00Z' });
        }
        await route.fulfill({ json: { dismissed, missing } });
    });
    await page.route((url) => url.pathname === '/api/diagnostics/dismissals/restore', async (route) => {
        const body = route.request().postDataJSON() as { ids: string[] };
        posts.push(`restore ${body.ids.join(',')}`);
        for (const entry of entries) if (body.ids.includes(entry.id)) entry.dismissedCount = undefined;
        await route.fulfill({ json: { restored: body.ids } });
    });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/system-health');
    await expect(page.getByRole('heading', { level: 1, name: 'Health' })).toBeVisible({ timeout: 15_000 });
    await expect(page.locator('[data-health-diagnostic]')).toHaveCount(2 + extra.length);
    return { entries, posts };
}

test('a warning can be dismissed, shown again under Show dismissed and restored, with the keyboard alone', async ({ page }) => {
    const { posts } = await openHealth(page);
    const status = page.locator('[data-health-status]');
    await expect(status.locator('[data-health-open-incident]')).toHaveCount(2);

    const backend = page.locator('[data-health-backend-diagnostics]');
    const dismiss = backend.locator('[data-health-diagnostic]').first().getByRole('button', { name: 'Dismiss' });
    // The button says what it does to whom, and that it comes back.
    await expect(dismiss).toHaveAccessibleDescription(/Hides this for everyone on this install\. Live checks carry on, and it shows again if it happens again\./);
    const box = await dismiss.boundingBox();
    expect(box && box.height >= 44).toBe(true);
    // Reached by Tab from the control before it, Clear error history, not by placing focus on it.
    await page.getByRole('button', { name: 'Clear error history' }).focus();
    await page.keyboard.press('Tab');
    await expect(dismiss).toBeFocused();
    await page.keyboard.press('Enter');

    // Gone from both lists and from the open count, kept under Show dismissed, which takes focus.
    await expect(backend.locator('[data-health-diagnostic]')).toHaveCount(1);
    await expect(status.locator('[data-health-open-incident]')).toHaveCount(1);
    const toggle = page.locator('[data-health-dismissed-toggle]');
    await expect(toggle).toHaveText('Show 1 dismissed');
    await expect(toggle).toBeFocused();
    await expect(page.locator('[data-health-dismiss-status]')).toHaveText('Dismissed. It shows again if it happens again.');
    expect(posts).toEqual(['dismiss diag:fixture:1×1']);

    await page.keyboard.press('Enter');
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(toggle).toHaveText('Hide dismissed');
    const dismissedList = page.locator('[data-health-dismissed-list]');
    await expect(dismissedList).toBeVisible();
    await expect(dismissedList.locator('[data-health-dismissed-item]')).toHaveCount(1);
    await expect(dismissedList).toContainText('Last happened');
    // The dismissed list is the foot of the card it came from, not a card of its own.
    await expect(backend.locator('[data-health-dismissed]')).toBeVisible();
    const restoreBox = await dismissedList.getByRole('button', { name: 'Restore' }).boundingBox();
    expect(restoreBox && restoreBox.height >= 44).toBe(true);

    await page.keyboard.press('Tab');
    const restore = dismissedList.getByRole('button', { name: 'Restore' });
    await expect(restore).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(backend.locator('[data-health-diagnostic]')).toHaveCount(2);
    await expect(status.locator('[data-health-open-incident]')).toHaveCount(2);
    await expect(page.locator('[data-health-dismissed]')).toHaveCount(0);
    expect(posts).toEqual(['dismiss diag:fixture:1×1', 'restore diag:fixture:1']);
    // The warning was the incident's only entry, so the incident was what Show dismissed listed;
    // focus returns to its Dismiss rather than to the top of the page.
    await expect(page.locator(':focus')).toHaveAttribute('data-health-dismiss-key', 'incident:event_processor:drop_classify_snapshot_timeout');
});

test('dismissing an open incident hides it and its warnings, and a new occurrence brings it back', async ({ page }) => {
    const { entries } = await openHealth(page);
    const status = page.locator('[data-health-status]');
    await status.locator('[data-health-open-incident]').first().getByRole('button', { name: 'Dismiss' }).click();

    await expect(status.locator('[data-health-open-incident]')).toHaveCount(1);
    await expect(page.locator('[data-health-backend-diagnostics] [data-health-diagnostic]')).toHaveCount(1);
    await expect(page.getByRole('button', { name: 'Show 1 dismissed' })).toBeVisible();

    // The server ends a dismissal when the fault is recorded again after it.
    const dismissed = entries.find((entry) => entry.dismissedCount !== undefined);
    expect(dismissed).toBeDefined();
    if (dismissed) Object.assign(dismissed, { count: 2, last_seen: '2026-11-18T07:59:00Z' });
    await page.reload();
    await expect(page.locator('[data-health-status] [data-health-open-incident]')).toHaveCount(2);
    await expect(page.locator('[data-health-dismissed]')).toHaveCount(0);
});

for (const theme of ['light', 'dark'] as const) {
    test(`Dismiss, Show dismissed and Restore pass the accessibility checks in ${theme}`, async ({ page }) => {
        await openHealth(page, { theme });
        await page.locator('[data-health-backend-diagnostics] [data-health-diagnostic]').first().getByRole('button', { name: 'Dismiss' }).click();
        await page.locator('[data-health-dismissed-toggle]').click();
        await expect(page.locator('[data-health-dismissed-list]')).toBeVisible();
        await settled(page);
        const results = await new AxeBuilder({ page }).include('main').analyze();
        expect(results.violations.map((violation) => `${violation.id}: ${violation.nodes.map((node) => node.target.join(' ')).join(', ')}`)).toEqual([]);
    });
}

test('an earlier incident dismissed is listed at the foot of Earlier incidents', async ({ page }) => {
    // A paused-video incident whose live check has since passed is an earlier incident.
    await openHealth(page, { extra: [
        { id: 'diag:fixture:3', component: 'video_classifier', reason_code: 'circuit_open', message: 'Video analysis paused', last_seen: '2026-11-18T06:00:00Z' }
    ] });
    const earlier = page.locator('[data-health-earlier-incidents]');
    await expect(earlier.locator('[data-health-earlier-incident]')).toHaveCount(1);
    await earlier.getByRole('button', { name: 'Dismiss' }).click();

    await expect(earlier.locator('[data-health-earlier-incident]')).toHaveCount(0);
    const toggle = earlier.locator('[data-health-dismissed-toggle]');
    await expect(toggle).toBeFocused();
    await expect(toggle).toHaveText('Show 1 dismissed');
    await expect(page.locator('[data-health-backend-diagnostics] [data-health-dismissed]')).toHaveCount(0);
});

test('a fault that happened again since the page loaded stays listed, and the page says so', async ({ page }) => {
    await openHealth(page, { beforeDismiss: (entries) => Object.assign(entries[0], { count: 2, last_seen: '2026-11-18T07:59:00Z' }) });
    const backend = page.locator('[data-health-backend-diagnostics]');
    const dismiss = backend.locator('[data-health-dismiss-key="entry:diag:fixture:1"]');
    await dismiss.click();

    await expect(backend.locator('[data-health-dismiss-notice="info"]')).toHaveText(/It happened again while this page was open, so it is still listed\./);
    await expect(backend.locator('[data-health-diagnostic]')).toHaveCount(2);
    await expect(page.locator('[data-health-dismiss-status]')).not.toHaveText(/Dismissed/);
    await expect(dismiss).toBeFocused();
});

test('an entry that had already left the history is not claimed as dismissed', async ({ page }) => {
    // Cleared in another tab, or lost in a restart, between the page's read and the click.
    await openHealth(page, { beforeDismiss: (entries) => { entries.splice(0, entries.length); } });
    const backend = page.locator('[data-health-backend-diagnostics]');
    await backend.locator('[data-health-dismiss-key="entry:diag:fixture:1"]').click();

    const notice = backend.locator('[data-health-dismiss-notice="info"]');
    await expect(notice).toHaveText(/This had already left the error history/);
    await expect(notice).toBeFocused();
    await expect(page.locator('[data-health-dismiss-status]')).not.toHaveText(/Dismissed/);
    await expect(page.locator('[data-health-dismissed]')).toHaveCount(0);
});

test('dismissing every item never turns a failing live check healthy', async ({ page }) => {
    await openHealth(page, { connections: {
        mqtt: { state: 'disconnected', server: 'mqtt.invalid', port: 1883, last_attempt_at: '2026-11-18T07:58:00Z', last_error_cause: 'host_not_found' },
        frigate: { state: 'reachable', url: 'http://frigate:5000', checked_at: '2026-11-18T07:59:00Z', availability: 'unknown' },
        generated_at: '2026-11-18T08:00:00Z'
    } });
    const status = page.locator('[data-health-status]');
    for (let remaining = 2; remaining > 0; remaining -= 1) {
        await status.locator('[data-health-open-incident]').first().getByRole('button', { name: 'Dismiss' }).click();
        await expect(status.locator('[data-health-open-incident]')).toHaveCount(remaining - 1);
    }
    await expect(status.locator('[data-health-problem="mqtt_down"]')).toBeVisible();
    await expect(status.locator('[data-health-status-pill]')).toHaveText('Degraded');
});

test('with every live check passing, dismissing the recorded incidents leaves the verdict to those checks', async ({ page }) => {
    // Documented expectation: recorded faults no longer counted, live checks all pass, so Healthy.
    await openHealth(page);
    const status = page.locator('[data-health-status]');
    await expect(status.locator('[data-health-status-pill]')).toHaveText('Degraded');
    for (let remaining = 2; remaining > 0; remaining -= 1) {
        await status.locator('[data-health-open-incident]').first().getByRole('button', { name: 'Dismiss' }).click();
        await expect(status.locator('[data-health-open-incident]')).toHaveCount(remaining - 1);
    }
    await expect(status.locator('[data-health-status-pill]')).toHaveText('Healthy');
});
