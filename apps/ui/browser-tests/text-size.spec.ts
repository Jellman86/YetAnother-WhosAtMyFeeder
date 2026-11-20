import { test, expect, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

// Set UI_SHOTS to a directory to keep review screenshots of the control.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

const rootSize = (page: Page): Promise<number> => page.evaluate(() => parseFloat(getComputedStyle(document.documentElement).fontSize));

const sizeSelect = (page: Page) => page.locator('[data-text-size-options]');

test('a chosen text size resizes the whole page and is kept on this device', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/browser-tests/text-size.html');
    const select = sizeSelect(page);
    await expect(select.locator('option')).toHaveCount(7);
    // Standard is the default, a step under the browser's own 16px.
    await expect(select).toHaveValue('standard');
    expect(await rootSize(page)).toBe(14);

    await select.selectOption({ label: 'Extra large' });
    await expect(select).toHaveValue('extra_large');
    expect(await rootSize(page)).toBe(20);
    await page.waitForTimeout(300);
    if (environment.UI_SHOTS) await page.screenshot({ path: `${environment.UI_SHOTS}/text-size-extra-large-1280.png` });

    await page.reload();
    await expect(sizeSelect(page)).toHaveValue('extra_large');
    expect(await rootSize(page)).toBe(20);

    await sizeSelect(page).selectOption('smallest');
    expect(await rootSize(page)).toBe(12);
    await sizeSelect(page).selectOption('large');
    expect(await rootSize(page)).toBe(16);
});

test('the size multiplies the growth on a large display rather than replacing it', async ({ page }) => {
    await page.setViewportSize({ width: 2304, height: 1200 });
    await page.goto('/browser-tests/text-size.html');
    expect(await rootSize(page)).toBe(17.5);
    await sizeSelect(page).selectOption('large');
    expect(await rootSize(page)).toBe(20);
});

test('a stored value the app does not know reads as standard', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('text_size', 'enormous'));
    await page.goto('/browser-tests/text-size.html');
    await expect(sizeSelect(page)).toHaveValue('standard');
    expect(await rootSize(page)).toBe(14);
});

for (const width of [320, 390]) {
    test(`the text size choice fits a ${width}px phone at the largest size with a usable target`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await page.goto('/browser-tests/text-size.html');
        await sizeSelect(page).selectOption('largest');
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        const box = await sizeSelect(page).boundingBox();
        expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
        expect((box?.x ?? -1) >= 0 && (box?.x ?? 0) + (box?.width ?? 0) <= width).toBe(true);
        if (environment.UI_SHOTS) await page.screenshot({ path: `${environment.UI_SHOTS}/text-size-largest-${width}.png` });
    });
}

/**
 * With Reduce Motion on (the system's or the app's own), Safari kept the old size for every word
 * inside an element whose transition the size change started, until the page was reloaded: each
 * transition was cut short rather than turned off, so every element ran one. A larger choice raises
 * the root and the small-print floor alike, so every word on show must grow, with motion or without.
 */
for (const motion of ['reduce', 'no-preference'] as const) {
    for (const width of [390, 1440]) {
        test(`a larger text size reaches every word on a ${width}px Settings page without a reload (reduced motion: ${motion})`, async ({ page }) => {
            await page.setViewportSize({ width, height: 900 });
            await replayFeeder(page, 'light');
            await page.emulateMedia({ reducedMotion: motion });
            await page.goto('/settings/appearance');
            await expect(sizeSelect(page)).toBeVisible({ timeout: 15_000 });
            await settled(page);
            const sizes = (): Promise<{ size: number; owner: string }[]> => page.evaluate(() => {
                const marked = window as unknown as { textOwners?: Element[] };
                if (!marked.textOwners) {
                    const owners = new Set<Element>();
                    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                    for (let node = walker.nextNode(); node; node = walker.nextNode()) {
                        const owner = node.parentElement;
                        const box = owner?.getBoundingClientRect();
                        if (owner && box && node.textContent?.trim() && box.width > 1 && box.height > 1 && !owner.closest('script, style, option, .sr-only') && owner.checkVisibility()) owners.add(owner);
                    }
                    marked.textOwners = [...owners];
                }
                return marked.textOwners.map((owner) => ({
                    size: parseFloat(getComputedStyle(owner).fontSize),
                    owner: `${owner.tagName.toLowerCase()}.${[...owner.classList].slice(0, 4).join('.')} "${(owner.textContent ?? '').trim().slice(0, 30)}"`
                }));
            });
            const before = await sizes();
            expect(before.length).toBeGreaterThan(20);
            await sizeSelect(page).selectOption('extra_large');
            await settled(page);
            const after = await sizes();
            const kept = before.filter((entry, index) => after[index].size <= entry.size).map((entry) => `${entry.size}px stayed: ${entry.owner}`);
            expect([...new Set(kept)]).toEqual([]);
        });
    }
}
