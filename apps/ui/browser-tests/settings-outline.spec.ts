import { expect, test, type Page } from '@playwright/test';

// Every Settings tab, every section open, read the way a screen reader lists headings: one page
// title, then no level skipped on the way down. Definition lists hold only terms and descriptions.

const TABS = ['connection', 'detection', 'integrations', 'ai', 'notifications', 'health', 'security', 'data', 'beta', 'appearance', 'accessibility'];

async function openOwnerShell(page: Page, width: number): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), (route) => {
        const path = new URL(route.request().url()).pathname;
        const responses: Record<string, unknown> = {
            '/api/auth/status': { auth_required: false, is_authenticated: true, needs_initial_setup: false },
            '/api/settings': { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false, cameras: ['patio'] },
            '/api/update-status': { update_available: false }
        };
        if (path in responses) return route.fulfill({ json: responses[path] });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in the outline fixture' } });
    });
    await page.route((url) => url.pathname === '/health', (route) => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width, height: 900 });
}

// Opens every closed section of the tab, nested ones too. Popover triggers are left alone.
async function openEverySection(page: Page): Promise<void> {
    for (let round = 0; round < 6; round += 1) {
        const closed = page.locator('[data-settings-content] button[aria-expanded="false"]:visible:not([aria-haspopup])');
        const count = await closed.count();
        if (count === 0) return;
        for (let index = count - 1; index >= 0; index -= 1) await closed.nth(index).click().catch(() => undefined);
    }
}

for (const width of [1440, 390]) {
    test(`at ${width}px every tab's headings descend one level at a time from the page title`, async ({ page }) => {
        test.setTimeout(120_000);
        await openOwnerShell(page, width);
        for (const tab of TABS) {
            await page.goto(`/settings/${tab}`);
            await expect(page.locator('[data-settings-content]')).toBeVisible({ timeout: 20_000 });
            await openEverySection(page);
            const outline = await page.locator('#main-content').evaluate((main) =>
                [...main.querySelectorAll('h1, h2, h3, h4, h5, h6')]
                    .filter((heading) => heading.checkVisibility())
                    .map((heading) => ({ level: Number(heading.tagName[1]), text: (heading.textContent ?? '').trim().slice(0, 40) })));
            expect(outline[0]?.level, `${tab} starts with the page title`).toBe(1);
            expect(outline.filter((heading) => heading.level === 1), `${tab} has one page title`).toHaveLength(1);
            const skips = outline.slice(1).filter((heading, index) => heading.level > outline[index].level + 1)
                .map((heading) => `${heading.text} (h${heading.level})`);
            expect(skips, `${tab} skips a heading level`).toEqual([]);

            const badLists = await page.locator('#main-content dl').evaluateAll((lists) => lists.flatMap((list) =>
                [...list.children].filter((child) => {
                    if (child.tagName === 'DT' || child.tagName === 'DD' || child.tagName === 'TEMPLATE' || child.tagName === 'SCRIPT') return false;
                    if (child.tagName !== 'DIV') return true;
                    return [...child.children].some((inner) => inner.tagName !== 'DT' && inner.tagName !== 'DD');
                }).map((child) => child.outerHTML.slice(0, 80))));
            expect(badLists, `${tab} has a definition list holding something other than terms and descriptions`).toEqual([]);
        }
    });
}
