import { expect, test } from '@playwright/test';
import { replayFeeder, settled, type Theme } from './accessibility-mock';

/**
 * The player is one object on its backdrop: a frame with an edge, a step apart from the backdrop in
 * both themes, holding the header, the picture and the controls. The picture is the darkest ground
 * in it, so a playing clip is the brightest thing on screen.
 */
const luminance = (colour: string): number => {
    const [red, green, blue] = (colour.match(/[\d.]+/g) ?? []).slice(0, 3).map(Number);
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
};

for (const theme of ['light', 'dark'] as Theme[]) {
    for (const size of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
        test(`the player has an edge and its controls inside its frame (${theme}, ${size.width}px)`, async ({ page }) => {
            await page.setViewportSize(size);
            await replayFeeder(page, theme);
            await page.route((url) => /\/api\/frigate\/[^/]+\/(?:recording-)?clip\.mp4$/.test(url.pathname), async (route) => {
                if (route.request().method() === 'HEAD') return route.fulfill({ status: 200 });
                await new Promise(() => {});
            });
            await page.goto('/events');
            await page.locator('button[aria-label^="Play video of"]').first().click({ timeout: 15_000 });
            const dialog = page.getByRole('dialog');
            await expect(dialog.getByRole('button', { name: 'Share link' })).toBeVisible({ timeout: 15_000 });
            await settled(page);

            const frame = dialog.locator('[data-video-player-frame]');
            const paint = await frame.evaluate((node) => {
                const style = getComputedStyle(node);
                const backdrop = getComputedStyle(node.closest('[role="dialog"]') as Element);
                return { ground: style.backgroundColor, edge: style.borderTopColor, edgeWidth: style.borderTopWidth, shadow: style.boxShadow, backdrop: backdrop.backgroundColor };
            });
            // An edge of its own, lighter than the frame it outlines, and a ground that is not the backdrop's.
            expect(paint.edgeWidth).toBe('1px');
            expect(luminance(paint.edge)).toBeGreaterThan(luminance(paint.ground) + 20);
            expect(paint.ground.replace(/\s/g, '')).not.toBe(paint.backdrop.replace(/\s/g, ''));
            expect(paint.shadow).not.toBe('none');

            // Header, picture and controls are one object.
            const box = await frame.boundingBox();
            for (const part of ['[data-video-player-header]', 'video', '[data-video-player-controls]']) {
                const inner = await dialog.locator(part).boundingBox();
                expect(box && inner && inner.x >= box.x - 1 && inner.y >= box.y - 1 && inner.x + inner.width <= box.x + box.width + 1 && inner.y + inner.height <= box.y + box.height + 1, part).toBe(true);
            }
            expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
        });
    }
}
