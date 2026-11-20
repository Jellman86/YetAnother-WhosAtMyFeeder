import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

// How Settings reads in the real shell: the section's name stays in view without being covered by
// the jobs strip, and headings share the left edge of the content under them.

/** A backfill under way, as the status push reports it, so the shell shows its jobs strip. */
const RUNNING_JOBS = {
    captured_at: new Date().toISOString(),
    items: [{
        id: 'backfill:backfill:fixture-running', event_id: null, kind: 'backfill', source: 'owner', status: 'running', phase: 'Importing missed visits',
        current: 40, total: 100, unit: 'detections', route: '/settings/data', created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
        finished_at: null, error: null, visibility: 'prominent'
    }],
    lanes: [{
        kind: 'backfill', queued: 3, running: 1, completed: 0, failed: 0, capacity: null,
        max_concurrent_configured: null, max_concurrent_effective: null, state: 'running', blocker: null
    }]
};

const box = async (page: Page, selector: string) => {
    const found = await page.locator(selector).first().boundingBox();
    if (!found) throw new Error(`${selector} is not on the page`);
    return found;
};

for (const [width, height] of [[1440, 900], [390, 844]] as const) {
    test.describe(`at ${width}px`, () => {
        test.use({ viewport: { width, height } });

        test('while a job runs, the jobs strip and the section name are both readable, one under the other', async ({ page }) => {
            await replayFeeder(page, 'light', { '/api/jobs': RUNNING_JOBS });
            await page.goto('/settings/identification');
            await expect(page.locator('[data-settings-content]')).toBeVisible({ timeout: 15_000 });
            await settled(page);
            const strip = page.locator('[data-jobs-strip]');
            await expect(strip.getByRole('region', { name: 'Jobs' })).toBeVisible();
            const heading = page.locator('[data-settings-section-heading]');
            await expect(heading).toHaveText('Identifying birds');

            // Scrolled into the section, both are stuck at the top.
            await page.mouse.move(width / 2, height / 2);
            await page.mouse.wheel(0, 1400);
            await expect.poll(() => page.evaluate(() => window.scrollY)).toBeGreaterThan(600);
            await expect.poll(async () => getComputedStyle_position(page)).toBe('sticky');
            await expect.poll(async () => {
                const [stripBox, headingBox] = [await box(page, '[data-jobs-strip]'), await box(page, '[data-settings-section-heading]')];
                return Math.round(headingBox.y - (stripBox.y + stripBox.height));
            }).toBeGreaterThanOrEqual(0);
            const [stripBox, headingBox] = [await box(page, '[data-jobs-strip]'), await box(page, '[data-settings-section-heading]')];
            // Stacked, touching, and both inside the window.
            expect(headingBox.y - (stripBox.y + stripBox.height)).toBeLessThanOrEqual(1);
            expect(stripBox.y).toBeGreaterThanOrEqual(0);
            expect(headingBox.y + headingBox.height).toBeLessThan(height / 2);
            // Nothing is drawn over the name: the element at its middle is the name itself.
            const onTop = await page.evaluate(() => {
                const name = document.querySelector('#settings-section-title');
                if (!name) return 'missing';
                const rect = name.getBoundingClientRect();
                const top = document.elementFromPoint(rect.left + Math.min(rect.width, 40) / 2, rect.top + rect.height / 2);
                return top === name || name.contains(top) ? 'name' : (top?.tagName ?? 'nothing');
            });
            expect(onTop).toBe('name');

            // Beside the settings, the search and the status column stay clear of the strip as well.
            if (width >= 1440) {
                const stripBottom = stripBox.y + stripBox.height;
                expect((await box(page, '[data-settings-search-input]')).y).toBeGreaterThanOrEqual(stripBottom);
                expect((await box(page, '[data-settings-aside="side"]')).y).toBeGreaterThanOrEqual(stripBottom);
            }

            // A control focused from the keyboard stops below both, not under them.
            const field = page.locator('#visit-gap-seconds');
            await field.focus();
            await expect.poll(async () => {
                const fieldBox = await field.boundingBox();
                const name = await box(page, '[data-settings-section-heading]');
                return Boolean(fieldBox && fieldBox.y >= name.y + name.height);
            }).toBe(true);
        });

        test('the section name, each group heading and the cards under them share one left edge', async ({ page }) => {
            await replayFeeder(page, 'light');
            await page.goto('/settings/cameras');
            await expect(page.locator('[data-settings-content]')).toBeVisible({ timeout: 15_000 });
            await settled(page);
            const edges = await page.evaluate(() => {
                const left = (element: Element | null): number | null => (element ? Math.round(element.getBoundingClientRect().left * 10) / 10 : null);
                const visible = (element: Element): boolean => (element as HTMLElement).checkVisibility();
                const content = document.querySelector('[data-settings-content]');
                return {
                    name: left(document.querySelector('#settings-section-title')),
                    status: left([...document.querySelectorAll('[data-settings-section-status] h3')].find(visible) ?? null),
                    groups: [...(content?.querySelectorAll('[data-settings-section] > header h3') ?? [])].filter(visible).map(left),
                    cards: [...(content?.querySelectorAll('[data-settings-section-body]') ?? [])].filter(visible).map(left)
                };
            });
            expect(edges.groups.length).toBeGreaterThan(1);
            expect(edges.cards.length).toBeGreaterThan(1);
            const all = [edges.name, ...edges.groups, ...edges.cards, ...(width < 700 ? [edges.status] : [])];
            for (const edge of all) expect(Math.abs((edge ?? -99) - (edges.name ?? 0)), JSON.stringify(edges)).toBeLessThanOrEqual(0.5);
        });
    });
}

/** Whether the jobs strip is stuck to the top yet: it sticks only once the page has scrolled. */
function getComputedStyle_position(page: Page): Promise<string> {
    return page.evaluate(() => {
        const strip = document.querySelector('[data-jobs-strip]');
        return strip ? getComputedStyle(strip).position : 'missing';
    });
}
