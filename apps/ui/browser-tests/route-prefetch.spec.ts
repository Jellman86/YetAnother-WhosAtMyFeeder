import { expect, test, type Page } from '@playwright/test';
import { replayFeeder } from './accessibility-mock';

// Pointing at a page's link in the sidebar, or reaching it with the keyboard, starts loading that
// page's code, so the click that follows shows the page without waiting for it.

function requestsFor(page: Page, moduleFile: string): () => number {
    let count = 0;
    page.on('request', (request) => {
        if (new URL(request.url()).pathname.endsWith(moduleFile)) count += 1;
    });
    return () => count;
}

const navLink = (page: Page, name: string) => page.locator('#app-sidebar').getByRole('button', { name, exact: true });

test('hovering a page link loads that page before the click', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    const speciesRequests = requestsFor(page, '/src/lib/pages/Species.svelte');
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 });
    expect(speciesRequests()).toBe(0);
    await navLink(page, 'Leaderboard').hover();
    await expect.poll(speciesRequests).toBeGreaterThan(0);
    await expect.poll(() => new URL(page.url()).pathname).toBe('/about');
});

test('reaching a page link with the keyboard loads that page before it is chosen', async ({ page }) => {
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    const explorerRequests = requestsFor(page, '/src/lib/pages/Events.svelte');
    await page.goto('/about');
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible({ timeout: 15_000 });
    const link = navLink(page, 'Explorer');
    await expect(link).toHaveCount(1);
    expect(explorerRequests()).toBe(0);
    await link.focus();
    await expect.poll(explorerRequests).toBeGreaterThan(0);
    await expect.poll(() => new URL(page.url()).pathname).toBe('/about');
});
