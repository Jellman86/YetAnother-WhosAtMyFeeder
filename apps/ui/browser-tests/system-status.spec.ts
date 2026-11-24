import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { HEALTHY_CONNECTIONS, replayFeeder, settled, type Theme } from './accessibility-mock';

/**
 * The sidebar's System status card in the real app shell: a neutral list of measured states,
 * one muted line of resource readings, and the way to Health. The link asks for
 * attention only for issues the Health page lists as open, and the two numbers always agree.
 */
const event = (component: string, reason: string, count = 1) => ({
    id: `diag:fixture:${component}`,
    source: 'fixture',
    component,
    reason_code: reason,
    message: `${component} could not finish its work`,
    severity: 'error',
    timestamp: new Date().toISOString(),
    count,
    first_seen: new Date(Date.now() - 3_600_000).toISOString(),
    last_seen: new Date().toISOString()
});

function workspace(events: ReturnType<typeof event>[]): Record<string, unknown> {
    return {
        '/api/diagnostics/workspace': {
            workspace_schema_version: 'fixture',
            backend_diagnostics: {
                captured_at: new Date().toISOString(),
                capacity: 500,
                total_events: events.length,
                total_occurrences: events.reduce((sum, item) => sum + item.count, 0),
                filtered_events: events.length,
                returned_events: events.length,
                severity_counts: {},
                component_counts: {},
                events
            },
            focused_diagnostics: {},
            health: { status: 'healthy' },
            // These cases are about incidents, so both connections are asked to be up.
            connections: HEALTHY_CONNECTIONS,
            classifier: {},
            taxonomy_repair: {},
            maintenance_coordinator: {},
            startup_warnings: []
        }
    };
}

const TWO_ISSUES = workspace([event('taxonomy_sync', 'request_failed', 14), event('weather', 'request_failed')]);

async function openShell(page: Page, theme: Theme, overrides: Record<string, unknown>, collapsed = false): Promise<void> {
    await page.addInitScript((value) => localStorage.setItem('sidebarCollapsed', value), String(collapsed));
    await replayFeeder(page, theme, overrides);
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/about');
    await expect(page.locator('[data-status-list]')).toBeVisible({ timeout: 15_000 });
    await settled(page);
}

/** What the Health page itself lists as open, counted from its own verdict card. */
async function openItemsOnHealth(page: Page): Promise<number> {
    await page.locator('[data-sidebar-status-link]').click();
    await expect(page.locator('[data-health-status]')).toBeVisible({ timeout: 15_000 });
    await settled(page);
    return page.locator('[data-health-problems] > li').count();
}

const card = (page: Page) => page.locator('[data-sidebar-status-card]');
const link = (page: Page) => page.locator('[data-sidebar-status-link]');

test('with nothing open the link is just "Health"', async ({ page }) => {
    await openShell(page, 'light', workspace([]));
    await expect(link(page)).toHaveAttribute('data-health-attention', 'false');
    await expect(link(page)).toHaveText('Health');
    await expect(card(page).locator('[data-health-issues]')).toHaveCount(0);
    expect(await openItemsOnHealth(page)).toBe(0);
});

test('open issues are counted on the link, and the Health page counts the same', async ({ page }) => {
    await openShell(page, 'light', TWO_ISSUES);
    await expect(link(page)).toHaveAttribute('data-health-attention', 'true');
    await expect(card(page).locator('[data-health-issues]')).toHaveText('2 issues need attention');
    await expect(link(page)).toHaveAccessibleName('Health: 2 issues need attention');
    expect(await openItemsOnHealth(page)).toBe(2);
    // A fault that repeated is one entry there, with how often and over what span.
    await expect(page.locator('[data-diagnostic-repeats]').first()).toContainText('×14, first');
});

test('the count is the link: one line, with the way in at its end', async ({ page }) => {
    await openShell(page, 'light', workspace([event('weather', 'request_failed')]));
    const issues = link(page).locator('[data-health-issues]');
    await expect(issues).toHaveText('1 issue needs attention');
    await expect(link(page)).toHaveAccessibleName('Health: 1 issue needs attention');
    // The count is the only visible wording, so nothing is left to drop onto a second line.
    await expect(link(page).getByText('Health', { exact: true })).toHaveCount(0);
    const line = await link(page).evaluate(node => {
        const words = node.querySelector('[data-health-issues]') as HTMLElement;
        const chevron = node.querySelector('[data-health-chevron]') as SVGElement;
        const wordsBox = words.getBoundingClientRect();
        const chevronBox = chevron.getBoundingClientRect();
        return {
            wordsLines: Math.round(wordsBox.height / parseFloat(getComputedStyle(words).lineHeight)),
            chevronOnTheWordsLine: chevronBox.top >= wordsBox.top - 1 && chevronBox.bottom <= wordsBox.bottom + 1,
            chevronAfterWords: chevronBox.left >= wordsBox.right
        };
    });
    expect(line).toEqual({ wordsLines: 1, chevronOnTheWordsLine: true, chevronAfterWords: true });
    await issues.click();
    await expect(page).toHaveURL(/\/system-health$/);
});

test('the card is a plain neutral surface with the load as named meters, not a link', async ({ page }) => {
    await openShell(page, 'light', workspace([]));
    await expect(card(page).getByRole('heading', { name: 'System status' })).toBeVisible();
    const readout = card(page).locator('[data-telemetry-readout]');
    // Each meter is named and says its figure, so the bar's length and colour are never the only cue.
    const meters = readout.locator('[data-telemetry-meter]');
    await expect(meters).toHaveText([/^\s*CPU\s*\d+%\s*$/, /^\s*NPU\s*\d+%\s*$/], { timeout: 15_000 });
    await expect(readout.locator('dt')).toHaveText(['CPU', 'NPU']);
    // The bars wear the Health chart's series colours: the CPU's and the first accelerator's, never one shared colour.
    const fills = await readout.locator('dd span[aria-hidden="true"] > span').evaluateAll((bars) => bars.map((bar) => getComputedStyle(bar).backgroundColor));
    expect(fills).toHaveLength(2);
    expect(fills[0]).not.toBe(fills[1]);
    const surface = await card(page).evaluate(node => {
        const style = getComputedStyle(node);
        const readout = node.querySelector('[data-telemetry-readout]') as HTMLElement;
        return {
            image: style.backgroundImage,
            layered: [...node.querySelectorAll('*')].some(el => getComputedStyle(el).position === 'absolute'),
            readoutIsLink: Boolean(readout.closest('a')),
            tabular: getComputedStyle(readout).fontVariantNumeric
        };
    });
    expect(surface).toEqual({ image: 'none', layered: false, readoutIsLink: false, tabular: 'lining-nums tabular-nums' });
    // Nothing in the card is wider than the card, and every pointer target is at least 24px.
    // Inline text and drawings have no box of their own to overflow; every box that has one is measured.
    const fits = await card(page).evaluate(node => [node, ...node.querySelectorAll<HTMLElement>('*')]
        .filter(el => el instanceof HTMLElement && getComputedStyle(el).display !== 'inline')
        .every(el => el.scrollWidth <= el.clientWidth + 1));
    expect(fits).toBe(true);
    expect((await link(page).boundingBox())?.height).toBeGreaterThanOrEqual(24);
});

test('the icon rail names each status and the Health link with the same words', async ({ page }) => {
    await openShell(page, 'light', TWO_ISSUES, true);
    await expect(card(page).getByRole('listitem')).toHaveCount(3);
    await expect(card(page).locator('[data-status-row="feed"]')).toHaveAttribute('title', /^Frigate events: /);
    await expect(link(page)).toHaveAccessibleName('Health: 2 issues need attention');
    await expect(link(page)).toHaveAttribute('title', 'Health: 2 issues need attention');
    const box = await link(page).boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(24);
    expect(box?.height).toBeGreaterThanOrEqual(24);
    const sidebar = await page.locator('#app-sidebar').boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual((sidebar?.x ?? 0) + (sidebar?.width ?? 0));
    await link(page).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/system-health$/);
});

test('a guest sees the status rows and no way into Health', async ({ page }) => {
    await openShell(page, 'light', {
        '/api/auth/status': { auth_required: true, public_access_enabled: true, is_authenticated: false, needs_initial_setup: false }
    });
    await expect(card(page).getByRole('listitem').first()).toBeVisible();
    await expect(link(page)).toHaveCount(0);
    await expect(card(page).locator('[data-status-row="alerts"]')).toHaveCount(0);
});

for (const theme of ['light', 'dark'] as const) {
    for (const collapsed of [false, true]) {
        test(`the ${collapsed ? 'icon rail' : 'card'} passes axe in the ${theme} theme with issues open`, async ({ page }) => {
            await openShell(page, theme, TWO_ISSUES, collapsed);
            const results = await new AxeBuilder({ page }).include('[data-sidebar-status]').analyze();
            expect(results.violations.map(violation => `${violation.id}: ${violation.nodes.map(node => node.target.join(' ')).join(', ')}`)).toEqual([]);
        });
    }
}

test('at 200% text the card loses nothing', async ({ page }) => {
    await openShell(page, 'light', TWO_ISSUES);
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%'; });
    await settled(page);
    // Nothing in the card is cut off: growing text pushes the card taller, and the column it is in scrolls,
    // rather than any box in the card hiding part of what it holds...
    const clipping = await card(page).evaluate(node => [node, ...node.querySelectorAll<HTMLElement>('*')]
        .filter(el => el instanceof HTMLElement && !el.classList.contains('sr-only') && getComputedStyle(el).overflow !== 'visible'
            && (el.scrollHeight > el.clientHeight + 1 || el.scrollWidth > el.clientWidth + 1))
        .map(el => el.outerHTML.slice(0, 80)));
    expect(clipping).toEqual([]);
    // ...and no box in it is wider than the card, so nothing runs out under the page.
    const tooWide = await card(page).evaluate(node => {
        const right = node.getBoundingClientRect().right;
        return [...node.querySelectorAll<HTMLElement>('*')]
            .filter(el => !el.classList.contains('sr-only') && el.getBoundingClientRect().right > right + 1)
            .map(el => el.outerHTML.slice(0, 80));
    });
    expect(tooWide).toEqual([]);
    await expect(card(page).locator('[data-health-issues]')).toBeVisible();
});

/** The status the replayed backend serves the page, read the way the page reads it. */
async function servedStatus(page: Page, overrides: Record<string, unknown>): Promise<{ overall: { state: string; cause: string; subsystem: string | null }; subsystems: { key: string; state: string }[] }> {
    await replayFeeder(page, 'light', overrides);
    await page.goto('/about');
    return page.evaluate(async () => (await fetch('/api/status')).json());
}

test('the replayed status keeps a failed workspace\'s failure', async ({ page }) => {
    const failing = workspace([]);
    const payload = failing['/api/diagnostics/workspace'] as Record<string, unknown>;
    payload.health = { status: 'degraded', event_pipeline: { status: 'degraded', critical_failure_active: true } };
    const status = await servedStatus(page, failing);
    expect(status.overall).toEqual({ state: 'degraded', cause: 'pipeline_critical', subsystem: null });
});

test('the replayed status never calls unmeasured connections healthy', async ({ page }) => {
    const status = await servedStatus(page, { '/api/diagnostics/connections': null });
    expect(status.overall.state).toBe('unknown');
    expect(status.subsystems.map((verdict) => verdict.state)).toEqual(['unknown', 'unknown']);
});

// Where the room under the places holds one line but not the card's floor, a one-line summary stands
// in for the card: the open issues as the card's own link counts them, or else the most important
// measured state in words, never a blanket "all fine".
const summary = (page: Page) => page.locator('[data-sidebar-status-summary]');
const summaryLink = (page: Page) => page.locator('[data-sidebar-summary-link]');

async function openShort(page: Page, theme: Theme, overrides: Record<string, unknown>): Promise<void> {
    await openShell(page, theme, overrides);
    // 48 px shorter than when Add observation was a place: the places end that much higher.
    await page.setViewportSize({ width: 1280, height: 612 });
    await expect(summary(page)).toBeVisible();
    await expect(card(page)).toBeHidden();
}

test('where only a line fits, the summary counts the open issues on its link, as the card does', async ({ page }) => {
    await openShort(page, 'light', TWO_ISSUES);
    await expect(summaryLink(page)).toHaveAccessibleName('Health: 2 issues need attention');
    await expect(summary(page).locator('[data-summary-issues]')).toHaveText('2 issues need attention');
    const box = await summaryLink(page).boundingBox();
    expect(box?.height).toBeGreaterThanOrEqual(24);
    await summaryLink(page).click();
    await expect(page).toHaveURL(/\/system-health$/);
});

test('with nothing open the summary names the feed in words, and links to Health', async ({ page }) => {
    await openShort(page, 'light', workspace([]));
    await expect(summaryLink(page)).toHaveAccessibleName(/^Health: Frigate events /);
    await expect(summary(page).locator('[data-summary-issues]')).toHaveCount(0);
    await expect(summary(page).locator('[data-summary-row="feed"]')).toBeVisible();
});

test('a guest gets the summary in words, and no way into Health', async ({ page }) => {
    await openShell(page, 'light', {
        '/api/auth/status': { auth_required: true, public_access_enabled: true, is_authenticated: false, needs_initial_setup: false }
    });
    // A guest has fewer places, so the line takes over lower down: shortened until it does.
    for (let height = 700; height >= 480 && !(await summary(page).isVisible()); height -= 8) {
        await page.setViewportSize({ width: 1280, height });
        await page.waitForTimeout(100);
    }
    await expect(summary(page)).toBeVisible();
    await expect(summaryLink(page)).toHaveCount(0);
    await expect(summary(page)).toContainText('Frigate events');
});

test('the summary is the one live region on show, so a change of tier is not said twice', async ({ page }) => {
    await openShort(page, 'light', workspace([]));
    const regions = page.getByRole('status');
    await expect(regions.filter({ has: page.locator('[data-summary-row]') })).toHaveCount(1);
    await expect(regions.filter({ has: page.locator('[data-status-list]') })).toHaveCount(0);
});

for (const theme of ['light', 'dark'] as const) {
    test(`the summary passes axe in the ${theme} theme with issues open`, async ({ page }) => {
        await openShort(page, theme, TWO_ISSUES);
        const results = await new AxeBuilder({ page }).include('[data-sidebar-status]').analyze();
        expect(results.violations.map(violation => `${violation.id}: ${violation.nodes.map(node => node.target.join(' ')).join(', ')}`)).toEqual([]);
    });
}

test('owner sidebar shows a detected GPU as Not measured before its first numeric reading (#1088)', async ({ page }) => {
    const base = workspace([]);
    await openShell(page, 'light', {
        ...base,
        '/api/status': {
            revision: 1,
            generated_at: new Date().toISOString(),
            startup_instance_id: 'fixture',
            version: 'unknown',
            overall: { state: 'ok', cause: 'ready', subsystem: null },
            subsystems: [
                { key: 'feed', state: 'ok', cause: 'connected' },
                { key: 'frigate', state: 'ok', cause: 'connected' }
            ],
            jobs_summary: { running: 0, queued: 0, progress: null },
            jobs: { captured_at: new Date().toISOString(), items: [], lanes: [] },
            analysis: { pending: 0, active: 0, circuit_open: false },
            model: { state: 'ok', cause: 'ready', revision: 'fixture' },
            connections: HEALTHY_CONNECTIONS,
            cameras: null,
            telemetry: {
                sampled_at: Date.now() / 1000,
                cpu_percent: 19.0,
                accelerator_kind: 'gpu',
                accelerator_label: 'Intel GPU',
                accelerator_percent: null
            },
            diagnostics_revision: 0,
            incident_revision: 'fixture',
            health_revision: 'fixture'
        }
    });
    const readout = card(page).locator('[data-telemetry-readout]');
    await expect(readout.locator('[data-telemetry-meter="cpu"]')).toContainText('19%');
    const gpu = readout.locator('[data-telemetry-meter="accelerator"]');
    await expect(gpu.locator('dt')).toHaveText('Intel GPU');
    await expect(gpu.locator('[data-telemetry-figure]')).toHaveText('Not measured');
});

test('guest sidebar shows a detected GPU as Not measured from live telemetry (#1088)', async ({ page }) => {
    await openShell(page, 'light', {
        '/api/auth/status': { auth_required: true, public_access_enabled: true, is_authenticated: false, needs_initial_setup: false },
        '/api/system-telemetry': {
            sampled_at: new Date().toISOString(),
            cpu_percent: 19.0,
            accelerator: { kind: 'gpu', label: 'Intel GPU', utilization_percent: null }
        }
    });
    const readout = card(page).locator('[data-telemetry-readout]');
    await expect(readout.locator('[data-telemetry-meter="cpu"]')).toContainText('19%');
    const gpu = readout.locator('[data-telemetry-meter="accelerator"]');
    await expect(gpu.locator('dt')).toHaveText('Intel GPU');
    await expect(gpu.locator('[data-telemetry-figure]')).toHaveText('Not measured');
});
