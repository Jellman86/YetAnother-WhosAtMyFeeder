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

interface LongLine { text: string; ch: number }

/** Every line box of running text on the page, measured in widths of "0" of its own font. */
async function longLines(page: Page): Promise<LongLine[]> {
    return page.evaluate((limit) => {
        const canvas = document.createElement('canvas').getContext('2d');
        const zeroWidth = new Map<string, number>();
        const found: { text: string; ch: number }[] = [];
        const main = document.querySelector('main');
        if (!main || !canvas) return found;
        const walker = document.createTreeWalker(main, NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const text = node.textContent ?? '';
            if (text.trim().length < 60) continue;
            const parent = node.parentElement;
            if (!parent || parent.closest('pre, code, svg, canvas, [aria-hidden="true"], .sr-only')) continue;
            const style = getComputedStyle(parent);
            if (style.visibility === 'hidden' || style.display === 'none') continue;
            const font = `${style.fontStyle} ${style.fontWeight} ${style.fontSize} ${style.fontFamily}`;
            if (!zeroWidth.has(font)) {
                canvas.font = font;
                zeroWidth.set(font, canvas.measureText('0').width);
            }
            const ch = zeroWidth.get(font) ?? 8;
            const range = document.createRange();
            range.selectNodeContents(node);
            // One rectangle per line the text node is broken onto.
            for (const rect of range.getClientRects()) {
                if (rect.width === 0 || rect.height === 0) continue;
                const width = rect.width / ch;
                if (width > limit) found.push({ text: text.trim().slice(0, 80), ch: Math.round(width) });
            }
        }
        return found;
    }, LONGEST_LINE_CH);
}

/** How much of the window the page's content spans, from its leftmost to its rightmost visible box. */
async function contentShare(page: Page): Promise<number> {
    return page.evaluate(() => {
        const main = document.querySelector('main');
        if (!main) return 0;
        let left = Infinity;
        let right = -Infinity;
        for (const element of main.querySelectorAll('*')) {
            const box = element.getBoundingClientRect();
            if (box.width === 0 || box.height === 0 || box.bottom < 0 || box.top > innerHeight * 2) continue;
            left = Math.min(left, box.left);
            right = Math.max(right, box.right);
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
            if (route.contentHeavy && size.width === 1920) {
                expect(await contentShare(page), 'share of the window the content spans').toBeGreaterThanOrEqual(0.7);
            }
        });
    }
}
