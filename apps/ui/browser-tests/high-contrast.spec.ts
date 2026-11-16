import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';
import recording from './fixtures/accessibility-api.json' with { type: 'json' };

/**
 * High contrast over the real app with a month of data on it, turned on in the light theme and in
 * the dark one, alone and with the reading font. The stylesheet test holds the rules; this holds
 * what a reader sees: every word on the page is measured against the ground it is drawn on.
 *
 * Over the light theme the mode once left headings, labels and the unsaved count near-black on its
 * black page, which no rule list or axe run had caught.
 */
const SAVED_SETTINGS = (recording as unknown as { responses: Record<string, { json: Record<string, unknown> }> }).responses['/api/settings'].json;
const READY = { timeout: 15_000 };

const PAGES: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
    { name: 'Settings › Accessibility', path: '/settings/accessibility', ready: (page) => expect(page.getByRole('switch', { name: 'High contrast' })).toBeVisible(READY) },
    { name: 'Settings › Appearance', path: '/settings/appearance', ready: (page) => expect(page.locator('[data-settings-content]')).toBeVisible(READY) },
    { name: 'the Dashboard', path: '/', ready: (page) => expect(page.locator('[data-field-log-row]').first()).toBeVisible(READY) },
    { name: 'the Explorer', path: '/events', ready: (page) => expect(page.locator('[data-detection-card], [data-detection-row]').first()).toBeVisible(READY) },
    { name: 'the Leaderboard', path: '/species', ready: (page) => expect(page.locator('[data-leaderboard-rankings]')).toBeVisible(READY) },
    { name: 'About', path: '/about', ready: (page) => expect(page.locator('#about-outbound-title')).toBeVisible(READY) }
];

interface Faint { text: string; ratio: number; ink: string; ground: string; element: string }

/**
 * Every run of visible text whose ink is under `floor`:1 against the ground beneath it. The ground
 * is the nearest opaque fill, with any translucent fills above it laid over it. Words drawn over a
 * picture or a gradient have no single ground and are left to the photo-chip rule.
 */
async function faintText(page: Page, floor: number): Promise<Faint[]> {
    return page.evaluate((minimum) => {
        type Rgba = [number, number, number, number];
        const parse = (value: string): Rgba => {
            const parts = value.match(/[\d.]+/g)?.map(Number) ?? [0, 0, 0, 0];
            return [parts[0], parts[1], parts[2], parts.length > 3 ? parts[3] : 1];
        };
        const over = (top: Rgba, under: Rgba): Rgba => {
            const alpha = top[3] + under[3] * (1 - top[3]);
            if (alpha === 0) return [0, 0, 0, 0];
            const mix = (index: 0 | 1 | 2) => (top[index] * top[3] + under[index] * under[3] * (1 - top[3])) / alpha;
            return [mix(0), mix(1), mix(2), alpha];
        };
        const luminance = ([red, green, blue]: Rgba) => {
            const channel = (value: number) => {
                const unit = value / 255;
                return unit <= 0.03928 ? unit / 12.92 : ((unit + 0.055) / 1.055) ** 2.4;
            };
            return 0.2126 * channel(red) + 0.7152 * channel(green) + 0.0722 * channel(blue);
        };
        const found: Faint[] = [];
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        const seen = new Set<Element>();
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
            const text = (node.textContent ?? '').trim();
            const element = node.parentElement;
            if (!text || !element || seen.has(element)) continue;
            seen.add(element);
            const style = getComputedStyle(element);
            const box = element.getBoundingClientRect();
            if (style.visibility !== 'visible' || box.width < 2 || box.height < 2) continue;
            if (element.closest('.sr-only, [aria-hidden="true"], .leaflet-container, canvas, svg')) continue;
            if (style.clipPath !== 'none' || style.position === 'absolute' && box.width <= 1) continue;
            let ground: Rgba = [0, 0, 0, 0];
            let opacity = 1;
            let overPicture = false;
            for (let ancestor: Element | null = element; ancestor; ancestor = ancestor.parentElement) {
                const ancestorStyle = getComputedStyle(ancestor);
                if (ancestorStyle.display === 'none') { opacity = 0; break; }
                opacity *= Number(ancestorStyle.opacity);
                if (ancestorStyle.backgroundImage !== 'none' || ancestor.querySelector(':scope > img, :scope > video, :scope > picture')) {
                    overPicture = ancestor !== document.documentElement && ancestor !== document.body;
                    if (overPicture) break;
                }
                if (ground[3] < 1) ground = over(ground, parse(ancestorStyle.backgroundColor));
            }
            if (overPicture || opacity === 0) continue;
            ground = over(ground, [0, 0, 0, 1]);
            const ink = parse(style.color);
            const drawn = over([ink[0], ink[1], ink[2], ink[3] * opacity], ground);
            const [lighter, darker] = [luminance(drawn), luminance(ground)].sort((first, second) => second - first);
            const ratio = (lighter + 0.05) / (darker + 0.05);
            if (ratio < minimum) {
                found.push({
                    text: text.slice(0, 40),
                    ratio: Math.round(ratio * 100) / 100,
                    ink: style.color,
                    ground: `rgb(${ground.slice(0, 3).map(Math.round).join(', ')})`,
                    element: `${element.tagName.toLowerCase()}.${String(element.getAttribute('class') ?? '').slice(0, 90)}`
                });
            }
        }
        return found;
    }, floor);
}

for (const theme of ['light', 'dark'] as Theme[]) {
    for (const readingFont of [false, true]) {
        const mode = `high contrast over the ${theme} theme${readingFont ? ' with the reading font' : ''}`;
        test.describe(mode, () => {
            test.use({ viewport: { width: 1440, height: 900 } });

            for (const target of PAGES) {
                test(`${target.name} keeps every word at 7:1 or better and passes axe`, async ({ page }) => {
                    await replayFeeder(page, theme, {
                        '/api/settings': { ...SAVED_SETTINGS, accessibility_high_contrast: true, accessibility_dyslexia_font: readingFont }
                    });
                    await page.goto(target.path);
                    await target.ready(page);
                    await settled(page);

                    // One black scheme: the dark variants apply whatever theme was chosen.
                    await expect(page.locator('html')).toHaveClass(/(?=.*\bhigh-contrast\b)(?=.*\bdark\b)/);
                    if (readingFont) await expect(page.locator('html')).toHaveClass(/\bfont-dyslexic\b/);
                    expect(await page.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe('rgb(0, 0, 0)');

                    expect(await faintText(page, 7)).toEqual([]);

                    const axe = await new AxeBuilder({ page }).analyze();
                    const serious = axe.violations
                        .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
                        .flatMap((violation) => violation.nodes.map((node) => `${violation.id}: ${node.target.join(' ')}`));
                    expect(serious).toEqual([]);
                });
            }
        });
    }
}

test('the theme switch still shows the reader\'s own theme while high contrast is on', async ({ page }) => {
    await replayFeeder(page, 'light', { '/api/settings': { ...SAVED_SETTINGS, accessibility_high_contrast: true } });
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    await expect(page.locator('html')).toHaveClass(/\bhigh-contrast\b/);
    // The light theme is still the choice on record, so the switch offers the dark one.
    await expect(page.getByRole('button', { name: 'Switch to dark mode' }).first()).toBeVisible(READY);
});
