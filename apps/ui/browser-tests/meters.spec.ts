import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';
import { measureMeters } from './meter-contrast';
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
    { name: 'the Leaderboard', path: '/species', ready: (page) => expect(page.locator('h1')).toBeVisible(READY) },
    {
        // The record's species-match bar, and any other score bar it draws, over the dialog's own ground.
        name: 'the detection record',
        path: '/',
        ready: async (page) => {
            await page.locator('[data-field-log-row]:not([data-field-log-garden]) button[data-field-log-action].btn-ghost').first().click(READY);
            await expect(page.locator('[data-record-score-bar]')).toBeVisible(READY);
        }
    }
];

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
