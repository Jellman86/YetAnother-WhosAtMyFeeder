import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';
import recording from './fixtures/accessibility-api.json' with { type: 'json' };

/**
 * Every meter as Chromium draws it: the fill's computed colour, flattened over its track when it
 * is translucent, against the track's computed colour, at 3:1 (WCAG 1.4.11), in both colour themes,
 * both modes and high contrast over each. A token test cannot see a translucent palette fill that
 * blends into its track; this measures what is on screen.
 */
const SAVED_SETTINGS = (recording as unknown as { responses: Record<string, { json: Record<string, unknown> }> }).responses['/api/settings'].json;
const READY = { timeout: 15_000 };

const COMBINATIONS: { name: string; colour: 'classic' | 'bluetit'; theme: Theme; highContrast: boolean }[] = [
    { name: 'classic light', colour: 'classic', theme: 'light', highContrast: false },
    { name: 'classic dark', colour: 'classic', theme: 'dark', highContrast: false },
    { name: 'bluetit light', colour: 'bluetit', theme: 'light', highContrast: false },
    { name: 'bluetit dark', colour: 'bluetit', theme: 'dark', highContrast: false },
    { name: 'high contrast over classic', colour: 'classic', theme: 'light', highContrast: true },
    { name: 'high contrast over bluetit', colour: 'bluetit', theme: 'light', highContrast: true }
];

const PAGES: { name: string; path: string; ready: (page: Page) => Promise<void> }[] = [
    { name: 'the Dashboard', path: '/', ready: (page) => expect(page.locator('[data-field-log-row]').first()).toBeVisible(READY) },
    { name: 'the Leaderboard', path: '/species', ready: (page) => expect(page.locator('h1')).toBeVisible(READY) }
];

type Measured = { meters: number; failures: string[] };

async function measureMeters(page: Page): Promise<Measured> {
    return page.evaluate(() => {
        // Any computed colour (rgb, oklab from a colour-mix) as sRGB with its alpha, through a canvas.
        const canvas = document.createElement('canvas');
        canvas.width = 1;
        canvas.height = 1;
        const context = canvas.getContext('2d', { willReadFrequently: true });
        if (!context) throw new Error('no 2d canvas');
        const parse = (value: string): [number, number, number, number] => {
            context.clearRect(0, 0, 1, 1);
            context.fillStyle = '#000';
            context.fillStyle = value;
            context.fillRect(0, 0, 1, 1);
            const [r, g, b, a] = context.getImageData(0, 0, 1, 1).data;
            return [r, g, b, a / 255];
        };
        const luminance = ([r, g, b]: number[]) => {
            const channel = (c: number) => { const s = c / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4; };
            return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
        };
        const contrast = (a: number[], b: number[]) => {
            const [x, y] = [luminance(a), luminance(b)];
            return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
        };
        const failures: string[] = [];
        let meters = 0;
        for (const track of document.querySelectorAll<HTMLElement>('.bg-track')) {
            const fill = [...track.children].find((child) => (child as HTMLElement).style.width) as HTMLElement | undefined;
            if (!fill || fill.getBoundingClientRect().width < 1) continue;
            meters += 1;
            const ground = parse(getComputedStyle(track).backgroundColor);
            const [r, g, b, a] = parse(getComputedStyle(fill).backgroundColor);
            const drawn = [r * a + ground[0] * (1 - a), g * a + ground[1] * (1 - a), b * a + ground[2] * (1 - a)];
            const ratio = contrast(drawn, ground);
            if (ratio < 3) {
                const where = fill.closest('[data-field-log-row], tr, li, section')?.textContent?.trim().slice(0, 40) ?? '';
                failures.push(`${getComputedStyle(fill).backgroundColor} on ${getComputedStyle(track).backgroundColor}: ${ratio.toFixed(2)} (${where})`);
            }
        }
        return { meters, failures };
    });
}

for (const combination of COMBINATIONS) {
    for (const surface of PAGES) {
        test(`every meter on ${surface.name} reads at 3:1 against its track in ${combination.name}`, async ({ page }) => {
            await page.setViewportSize({ width: 1440, height: 1100 });
            await replayFeeder(page, combination.theme, combination.highContrast ? { '/api/settings': { ...SAVED_SETTINGS, accessibility_high_contrast: true } } : {});
            await page.addInitScript((colour) => localStorage.setItem('color_theme', colour), combination.colour);
            await page.goto(surface.path);
            await surface.ready(page);
            await settled(page);
            if (combination.highContrast) await expect(page.locator('html')).toHaveClass(/\bhigh-contrast\b/);
            await expect(page.locator('html')).toHaveClass(combination.colour === 'bluetit' ? /\btheme-bluetit\b/ : /^(?!.*\btheme-bluetit\b)/);
            const measured = await measureMeters(page);
            expect(measured.meters, 'meters measured').toBeGreaterThan(0);
            expect(measured.failures).toEqual([]);
        });
    }
}
