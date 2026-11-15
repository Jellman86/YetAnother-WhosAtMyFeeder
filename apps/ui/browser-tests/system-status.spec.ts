import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';

/**
 * The sidebar's System status card in the real app shell: a neutral list of measured states,
 * one muted line of resource readings, and the way to System health. The link asks for
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

/** What the Health page itself counts as open, read from its own "N open" badge. */
async function openIssuesOnHealth(page: Page): Promise<number> {
    await page.locator('[data-sidebar-status-link]').click();
    const badge = page.locator('[data-health-current-issues]').getByText(/^\d[\d,]* open$/);
    await expect(badge).toBeVisible({ timeout: 15_000 });
    return Number(((await badge.textContent()) ?? '').replace(/\D/g, ''));
}

const card = (page: Page) => page.locator('[data-sidebar-status-card]');
const link = (page: Page) => page.locator('[data-sidebar-status-link]');

test('with nothing open the link is just "System health"', async ({ page }) => {
    await openShell(page, 'light', workspace([]));
    await expect(link(page)).toHaveAttribute('data-health-attention', 'false');
    await expect(link(page)).toHaveText('System health');
    await expect(card(page).locator('[data-health-issues]')).toHaveCount(0);
    expect(await openIssuesOnHealth(page)).toBe(0);
});

test('open issues are counted on the link, and the Health page counts the same', async ({ page }) => {
    await openShell(page, 'light', TWO_ISSUES);
    await expect(link(page)).toHaveAttribute('data-health-attention', 'true');
    await expect(card(page).locator('[data-health-issues]')).toHaveText('2 issues need attention');
    await expect(link(page)).toHaveAccessibleName('2 issues need attention System health');
    expect(await openIssuesOnHealth(page)).toBe(2);
    // A fault that repeated is one entry there, with how often and over what span.
    await expect(page.locator('[data-diagnostic-repeats]').first()).toContainText('×14, first');
});

test('the card is a plain neutral surface with the readings as text, not a link', async ({ page }) => {
    await openShell(page, 'light', workspace([]));
    await expect(card(page).getByRole('heading', { name: 'System status' })).toBeVisible();
    const readout = card(page).locator('[data-telemetry-readout]');
    await expect(readout).toHaveText(/^\s*CPU \d+%\s*·\s*NPU \d+%\s*$/, { timeout: 15_000 });
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
    expect(surface).toEqual({ image: 'none', layered: false, readoutIsLink: false, tabular: 'tabular-nums' });
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
    await expect(link(page)).toHaveAccessibleName('System health: 2 issues need attention');
    await expect(link(page)).toHaveAttribute('title', 'System health: 2 issues need attention');
    const box = await link(page).boundingBox();
    expect(box?.width).toBeGreaterThanOrEqual(24);
    expect(box?.height).toBeGreaterThanOrEqual(24);
    const sidebar = await page.locator('#app-sidebar').boundingBox();
    expect((box?.x ?? 0) + (box?.width ?? 0)).toBeLessThanOrEqual((sidebar?.x ?? 0) + (sidebar?.width ?? 0));
    await link(page).focus();
    await page.keyboard.press('Enter');
    await expect(page).toHaveURL(/\/settings\/health$/);
});

test('a guest sees the status rows and no way into System health', async ({ page }) => {
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
    // Nothing in the card clips or scrolls, so growing text can only push the card taller...
    const clipping = await card(page).evaluate(node => [node, ...node.querySelectorAll<HTMLElement>('*')]
        .filter(el => el instanceof HTMLElement && !el.classList.contains('sr-only') && getComputedStyle(el).overflow !== 'visible')
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
