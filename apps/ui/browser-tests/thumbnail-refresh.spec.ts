import { test, expect, type Page, type Route } from '@playwright/test';

// Boundary fixture: the real list surfaces (detection card, Needs your call card, visit
// preview, notifications), with every image supplied here. Proves that a settled
// reclassification gives that capture's thumbnails a new URL and nothing else does. It is not
// backend or cache E2E.

const SURFACES = ['card', 'queue-card', 'preview', 'notifications'];

interface Plan { requests: string[]; missing: Set<string>; errors: string[] }

function svg(fill: string): string {
    return `<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64"><rect width="64" height="64" fill="${fill}"/></svg>`;
}

async function open(page: Page, missing: string[] = []): Promise<Plan> {
    const plan: Plan = { requests: [], missing: new Set(missing), errors: [] };
    page.on('pageerror', (error) => plan.errors.push(error.message));
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route((url) => url.pathname.startsWith('/api/'), async (route: Route) => {
        const url = new URL(route.request().url());
        const requested = `${url.pathname}${url.search}`;
        plan.requests.push(requested);
        if (url.pathname.endsWith('/thumbnail.jpg')) {
            if (plan.missing.has(requested)) return route.fulfill({ status: 404, body: '' });
            return route.fulfill({ contentType: 'image/svg+xml', body: svg(url.search ? '#0f766e' : '#7c2d12') });
        }
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/thumbnail-refresh.html', { waitUntil: 'domcontentloaded' });
    await expect(page.locator('[data-surface="notifications"] img')).toHaveCount(2);
    return plan;
}

/** Which surface draws which URL for one capture, in a stable order. */
async function thumbnails(page: Page, id: string): Promise<Record<string, string>> {
    return page.evaluate((capture) => {
        const drawn: Record<string, string> = {};
        for (const image of document.querySelectorAll('img')) {
            const src = image.getAttribute('src') ?? '';
            if (!src.includes(`/frigate/${capture}/thumbnail.jpg`)) continue;
            const surface = image.closest('[data-surface]')?.getAttribute('data-surface') ?? 'portal';
            drawn[surface.replace(/-[AB]$/, '')] = src;
        }
        return drawn;
    }, id);
}

function thumbnailRequests(plan: Plan, id: string): number {
    return plan.requests.filter((request) => request.includes(`/frigate/${id}/thumbnail.jpg`)).length;
}

test('a settled run gives only that capture a fresh thumbnail on every list surface', async ({ page }) => {
    const plan = await open(page);
    await expect.poll(async () => Object.keys(await thumbnails(page, 'A')).sort()).toEqual([...SURFACES].sort());
    const before = await thumbnails(page, 'A');
    for (const src of Object.values(before)) expect(src).toMatch(/\/api\/frigate\/A\/thumbnail\.jpg$/);
    const requestsBefore = thumbnailRequests(plan, 'A');

    // A running analysis of A and another capture finishing are not A's photograph changing.
    await page.evaluate(() => {
        window.thumbnailRefresh?.progressAnalysis('A', 12);
        window.thumbnailRefresh?.completeAnalysis('B');
    });
    await expect.poll(async () => Object.values(await thumbnails(page, 'B'))).toContain('/api/frigate/B/thumbnail.jpg?v=1');
    await page.waitForTimeout(150);
    expect(await thumbnails(page, 'A')).toEqual(before);
    expect(thumbnailRequests(plan, 'A')).toBe(requestsBefore);

    // Versions come from one sequence for the page, so A's run, settling after B's, is v=2.
    await page.evaluate(() => window.thumbnailRefresh?.completeAnalysis('A'));
    await expect.poll(() => thumbnails(page, 'A')).toEqual(
        Object.fromEntries(SURFACES.map((surface) => [surface, '/api/frigate/A/thumbnail.jpg?v=2']))
    );
    await expect.poll(() => thumbnailRequests(plan, 'A')).toBeGreaterThan(requestsBefore);
    expect(plan.errors).toEqual([]);
});

test('the visit preview panel shows the settled photograph', async ({ page }) => {
    const plan = await open(page);
    await page.evaluate(() => window.thumbnailRefresh?.completeAnalysis('A'));
    await page.locator('[data-surface="preview"] button').first().focus();
    await expect(page.locator('[data-detection-preview-panel] img')).toHaveAttribute('src', '/api/frigate/A/thumbnail.jpg?v=1');
    expect(plan.errors).toEqual([]);
});

test('a thumbnail missing before the run is tried again once the run has saved one', async ({ page }) => {
    const plan = await open(page, ['/api/frigate/A/thumbnail.jpg']);
    await expect.poll(async () => Object.keys(await thumbnails(page, 'A'))).toEqual(['notifications']);
    await page.evaluate(() => window.thumbnailRefresh?.completeAnalysis('A'));
    await expect.poll(async () => Object.keys(await thumbnails(page, 'A')).sort()).toEqual([...SURFACES].sort());
    for (const surface of SURFACES) {
        await expect(page.locator(`[data-surface^="${surface}"] img[src="/api/frigate/A/thumbnail.jpg?v=1"]`).first()).toBeVisible();
    }
    expect(plan.errors).toEqual([]);
});
