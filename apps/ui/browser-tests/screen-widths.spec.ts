import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * The width guard (layout-patterns, "Width bands"): every route at the five widths the app is
 * judged at. On each, the page never scrolls sideways and no line of text runs past about 80
 * characters; at 1920 px the content-heavy pages use about 70% or more of the window. One pass of
 * measurements per route and width, so the whole set stays quick.
 */
const READY = { timeout: 15_000 };
const WIDTHS = [
    { width: 390, height: 844 },
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 }
];

const ROUTES: { name: string; path: string; ready: string; contentHeavy?: boolean }[] = [
    { name: 'Dashboard', path: '/', ready: '[data-field-log-row]', contentHeavy: true },
    { name: 'Explorer', path: '/events', ready: '[data-detection-card], [data-detection-row]', contentHeavy: true },
    // /garden opens the Explorer on the Garden visitors.
    { name: 'Garden', path: '/garden', ready: 'main h1' },
    { name: 'Leaderboard', path: '/species', ready: '[data-capture-wall-segment]', contentHeavy: true },
    { name: 'Audio history', path: '/audio', ready: '[data-audio-top-species-button]' },
    { name: 'Notifications', path: '/notifications', ready: '[data-notifications-timeline]' },
    { name: 'About', path: '/about', ready: '#about-outbound-title' },
    { name: 'Add observation', path: '/observations/new', ready: 'main h1' },
    { name: 'Model evaluation', path: '/diagnostics/model-eval', ready: '[data-model-evaluation]' },
    { name: 'Health', path: '/system-health', ready: '[data-health-timeline]' },
    { name: 'Settings', path: '/settings', ready: '[data-settings-content]', contentHeavy: true }
];

/** About 80 characters: a line wider than this many widths of "0" in its own font is too long. */
const LONGEST_LINE_CH = 82;

/**
 * Lines known to run long in parts this work does not own. Each names its owner; take it off the
 * list when its measure is fixed. The list may only shrink.
 */
const KNOWN_LONG_LINES: { route: string; startsWith: string; owner: string }[] = [
    { route: 'Health', startsWith: 'CPU and memory are read from this container', owner: 'Settings (M4): components/settings/SystemHealthPanel.svelte, the resource note' },
    { route: 'Settings', startsWith: 'Optional CPU scans of retained motion footage', owner: 'Settings (M4): components/settings/CameraWatchRow.svelte, the motion help' }
];

/** Content-heavy pages known to use less of a 1920 px window, with their owner. The list may only shrink. */
const KNOWN_NARROW: { route: string; owner: string }[] = [
    { route: 'Settings', owner: 'Settings (M4): the content column and status column end about 360 px short of the window at 1920 px' }
];

interface LongLine { text: string; ch: number }

/**
 * Every line of running text on the page, measured in widths of "0" of its block's font. Each block
 * that holds text of its own (a paragraph, a list item, a cell) is measured whole, its line boxes
 * grouped by line, so a line built from several text nodes (a bold lead-in and the sentence after it)
 * is measured as the reader sees it. A flex or grid row is not a line of text: its parts are measured
 * as their own blocks.
 */
async function longLines(page: Page): Promise<LongLine[]> {
    return page.evaluate((limit) => {
        const canvas = document.createElement('canvas').getContext('2d');
        const zeroWidth = new Map<string, number>();
        const found: { text: string; ch: number }[] = [];
        const main = document.querySelector('main');
        if (!main || !canvas) return found;
        const holdsText = (element: Element): boolean =>
            [...element.childNodes].some((child) => child.nodeType === Node.TEXT_NODE && (child.textContent ?? '').trim().length > 0);
        for (const block of main.querySelectorAll('*')) {
            if (!holdsText(block) || block.closest('pre, code, svg, canvas, [aria-hidden="true"], .sr-only')) continue;
            const style = getComputedStyle(block);
            if (style.visibility === 'hidden' || style.display === 'none' || style.display.startsWith('inline')) continue;
            if (style.display.includes('flex') || style.display.includes('grid')) continue;
            const font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
            if (!zeroWidth.has(font)) {
                canvas.font = font;
                zeroWidth.set(font, canvas.measureText('0').width);
            }
            const ch = zeroWidth.get(font) ?? 8;
            const range = document.createRange();
            range.selectNodeContents(block);
            const lines = new Map<number, { left: number; right: number }>();
            for (const rect of range.getClientRects()) {
                if (rect.width === 0 || rect.height === 0) continue;
                const key = Math.round((rect.top + rect.bottom) / 2 / 6);
                const line = lines.get(key) ?? { left: Infinity, right: -Infinity };
                line.left = Math.min(line.left, rect.left);
                line.right = Math.max(line.right, rect.right);
                lines.set(key, line);
            }
            for (const line of lines.values()) {
                const width = (line.right - line.left) / ch;
                if (width > limit) found.push({ text: (block.textContent ?? '').trim().replace(/\s+/g, ' ').slice(0, 80), ch: Math.round(width) });
            }
        }
        return found;
    }, LONGEST_LINE_CH);
}

/**
 * How much of the window the page's content spans: the union of what paints, not of the wrappers
 * that always span the page. Content is a picture, a chart or a drawing, a card or panel (anything
 * with its own ground or rule), and every run of text. The page header's small controls are not.
 */
async function contentShare(page: Page): Promise<number> {
    return page.evaluate(() => {
        const main = document.querySelector('main');
        if (!main) return 0;
        let left = Infinity;
        let right = -Infinity;
        const take = (box: DOMRect): void => {
            if (box.width === 0 || box.height === 0 || box.bottom < 0 || box.top > innerHeight * 2) return;
            left = Math.min(left, box.left);
            right = Math.max(right, box.right);
        };
        const transparent = (colour: string): boolean => colour === 'transparent' || /rgba\([^)]*,\s*0\)$/.test(colour);
        for (const element of main.querySelectorAll('*')) {
            if (element.closest('.sr-only, [aria-hidden="true"]')) continue;
            const box = element.getBoundingClientRect();
            const tag = element.tagName.toLowerCase();
            if (tag === 'img' || tag === 'canvas' || tag === 'video' || (tag === 'svg' && box.width >= 48 && box.height >= 48)) {
                take(box);
                continue;
            }
            if (box.width < 120 || box.height < 24) continue;
            const style = getComputedStyle(element);
            const ruled = ['Top', 'Right', 'Bottom', 'Left'].filter((side) => parseFloat(style.getPropertyValue(`border-${side.toLowerCase()}-width`)) > 0).length >= 2;
            if (!transparent(style.backgroundColor) || ruled) take(box);
        }
        const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            if (!(node.textContent ?? '').trim() || node.parentElement?.closest('.sr-only, [aria-hidden="true"]')) continue;
            const range = document.createRange();
            range.selectNodeContents(node);
            for (const rect of range.getClientRects()) take(rect);
        }
        return right > left ? (right - left) / innerWidth : 0;
    });
}

for (const route of ROUTES) {
    for (const size of WIDTHS) {
        test(`${route.name} at ${size.width} px: no sideways scroll, no line past about 80 characters${route.contentHeavy && size.width === 1920 ? ', and the width in use' : ''}`, async ({ page }) => {
            await page.setViewportSize(size);
            await replayFeeder(page, 'light');
            await page.goto(route.path);
            await expect(page.locator(route.ready).first()).toBeVisible(READY);
            await settled(page);

            expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth), 'sideways scroll').toBeLessThanOrEqual(0);
            const known = KNOWN_LONG_LINES.filter((line) => line.route === route.name).map((line) => line.startsWith);
            const long = (await longLines(page)).filter((line) => !known.some((start) => line.text.startsWith(start)));
            expect(long, 'lines longer than about 80 characters').toEqual([]);
            if (route.contentHeavy && size.width === 1920 && !KNOWN_NARROW.some((entry) => entry.route === route.name)) {
                expect(await contentShare(page), 'share of the window the content spans').toBeGreaterThanOrEqual(0.7);
            }
        });
    }
}

test('the fill measure fails a page whose content is held to a narrow column', async ({ page }) => {
    await page.setViewportSize({ width: 1920, height: 1080 });
    await replayFeeder(page, 'light');
    await page.goto('/');
    await expect(page.locator('[data-field-log-row]').first()).toBeVisible(READY);
    await settled(page);
    expect(await contentShare(page)).toBeGreaterThanOrEqual(0.7);
    await page.addStyleTag({ content: 'main > * { max-width: 40rem !important; }' });
    expect(await contentShare(page)).toBeLessThan(0.7);
});

for (const known of KNOWN_LONG_LINES) {
    test(`the known long line on ${known.route} is still there, so its entry is still needed`, async ({ page }) => {
        const route = ROUTES.find((entry) => entry.name === known.route);
        expect(route, known.route).toBeTruthy();
        if (!route) return;
        await page.setViewportSize({ width: 1920, height: 1080 });
        await replayFeeder(page, 'light');
        await page.goto(route.path);
        await expect(page.locator(route.ready).first()).toBeVisible(READY);
        await settled(page);
        // An entry whose line has been fixed must come off the list: the list may only shrink.
        expect((await longLines(page)).some((line) => line.text.startsWith(known.startsWith)), known.owner).toBe(true);
    });
}

for (const known of KNOWN_NARROW) {
    test(`${known.route} still uses less than 70% of a 1920 px window, so its entry is still needed`, async ({ page }) => {
        const route = ROUTES.find((entry) => entry.name === known.route);
        expect(route, known.route).toBeTruthy();
        if (!route) return;
        await page.setViewportSize({ width: 1920, height: 1080 });
        await replayFeeder(page, 'light');
        await page.goto(route.path);
        await expect(page.locator(route.ready).first()).toBeVisible(READY);
        await settled(page);
        expect(await contentShare(page), known.owner).toBeLessThan(0.7);
    });
}

