import { expect, test, type Page } from '@playwright/test';
import { replayFeeder, settled } from './accessibility-mock';

// "/" focuses a page's search in the real shell, where the app's own shortcuts listen first. German,
// Spanish, Italian, Portuguese and French keyboards type "/" with Shift, and that is still "/".

test.use({ viewport: { width: 1440, height: 900 } });

/** A key press as such a keyboard sends it: the key is "/", with Shift held. */
const pressSlashWithShift = (page: Page) => page.evaluate(() => {
    (document.activeElement ?? document.body).dispatchEvent(new KeyboardEvent('keydown', { key: '/', code: 'Digit7', shiftKey: true, bubbles: true, cancelable: true }));
});

const shortcutsPanel = (page: Page) => page.getByRole('dialog', { name: 'Keyboard shortcuts' });

for (const { name, path, input, ready } of [
    { name: 'Settings', path: '/settings/cameras', input: '[data-settings-search-input]', ready: '[data-settings-content]' },
    { name: 'the Explorer', path: '/events', input: '#explorer-search-input', ready: '[data-detection-card], [data-detection-row]' }
]) {
    test(`on ${name}, "/" typed with Shift focuses the search and does not open the shortcuts panel`, async ({ page }) => {
        await replayFeeder(page, 'light');
        await page.goto(path);
        await expect(page.locator(ready).first()).toBeVisible({ timeout: 15_000 });
        await settled(page);
        await page.locator('#main-content').click({ position: { x: 5, y: 5 } });
        await pressSlashWithShift(page);
        await expect(page.locator(input)).toBeFocused();
        await expect(shortcutsPanel(page)).toHaveCount(0);
        // Plain "/" does the same, and "?" still opens the panel.
        await page.locator(input).blur();
        await page.keyboard.press('/');
        await expect(page.locator(input)).toBeFocused();
        await page.locator(input).blur();
        await page.keyboard.press('Shift+?');
        await expect(shortcutsPanel(page)).toBeVisible();
    });
}
