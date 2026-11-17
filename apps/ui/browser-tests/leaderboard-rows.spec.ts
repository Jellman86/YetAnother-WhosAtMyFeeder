import { expect, test } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

/**
 * Every ranking row shows this feeder's own photograph of the species where there is one (its
 * portrait, else its newest visit on the wall), then the species' reference picture, and otherwise
 * nothing: never a stand-in feather that says nothing about the bird.
 */
const READY = { timeout: 15_000 };
const PORTRAIT = '/api/leaderboard/portraits/blue-tit-crop.jpg';

test('ranking rows show the feeder\'s own crop, and no stand-in icon where there is no picture', async ({ page }) => {
    await page.setViewportSize({ width: 1440, height: 1100 });
    await replayFeeder(page, 'light', {
        '/api/leaderboard/portraits': {
            span: 'month',
            portraits: [{ species: 'Eurasian Blue Tit', scientific_name: 'Cyanistes caeruleus', taxa_id: 144849, frigate_event: 'blue-tit-visit', image_url: PORTRAIT, film_url: null }]
        }
    });
    await page.goto('/species');
    const portraits = page.locator('[data-leaderboard-species-portrait]');
    await expect(portraits.first()).toBeVisible(READY);
    await settled(page);

    // The leader's row shows its own crop from the portraits route.
    const leader = page.locator('[data-leaderboard-table-rankings] tbody tr').first();
    await expect(leader.locator('[data-leaderboard-species-portrait="photo"] img')).toHaveAttribute('src', /\/api\/leaderboard\/portraits\/blue-tit-crop\.jpg/);

    // No row draws an icon in place of a picture.
    await expect(page.locator('[data-leaderboard-species-portrait] svg')).toHaveCount(0);
    const empty = page.locator('[data-leaderboard-species-portrait="none"]');
    for (const slot of await empty.all()) await expect(slot.locator('*')).toHaveCount(0);
});
