import { expect, test, type Page } from '@playwright/test';
import recording from './fixtures/accessibility-api.json' with { type: 'json' };
import { replayFeeder, settled } from './accessibility-mock';

/**
 * Accessibility is chosen per device: what the owner saved is the default that guests and new
 * devices follow, and a choice made under Display on one browser changes that browser at once,
 * outlasts a reload and never touches the saved settings.
 */
const SAVED_SETTINGS = (recording as unknown as { responses: Record<string, { json: Record<string, unknown> }> }).responses['/api/settings'].json;

const thisDevice = (page: Page) => page.locator('[data-settings-part="accessibility"]');
const html = (page: Page) => page.locator('html');

async function openDisplay(page: Page, saved: Record<string, unknown>): Promise<string[]> {
    const writes: string[] = [];
    page.on('request', (request) => {
        if (request.method() !== 'GET' && new URL(request.url()).pathname === '/api/settings') writes.push(request.url());
    });
    await replayFeeder(page, 'light', { '/api/settings': { ...SAVED_SETTINGS, ...saved } });
    await page.goto('/settings/display');
    await expect(thisDevice(page).getByRole('switch', { name: 'High contrast' })).toBeVisible({ timeout: 15_000 });
    await settled(page);
    return writes;
}

test.use({ viewport: { width: 1440, height: 900 } });

test('a device with no choice of its own follows the saved default', async ({ page }) => {
    await openDisplay(page, { accessibility_high_contrast: true, accessibility_reduced_motion: false });
    await expect(html(page)).toHaveClass(/\bhigh-contrast\b/);
    const highContrast = thisDevice(page).getByRole('switch', { name: 'High contrast' });
    await expect(highContrast).toHaveAttribute('aria-checked', 'true');
    await expect(thisDevice(page).locator('#setting-high-contrast-source')).toHaveText('Follows the default for everyone (on)');
    await expect(thisDevice(page).getByRole('button', { name: 'Use the default' })).toHaveCount(0);
});

test('a choice on this device changes it at once, needs no saving and outlasts a reload', async ({ page }) => {
    const writes = await openDisplay(page, { accessibility_high_contrast: true });
    const highContrast = thisDevice(page).getByRole('switch', { name: 'High contrast' });
    await highContrast.click();
    await expect(html(page)).not.toHaveClass(/\bhigh-contrast\b/);
    await expect(highContrast).toHaveAttribute('aria-checked', 'false');
    await expect(thisDevice(page).locator('#setting-high-contrast-source')).toHaveText('Set on this device. The default for everyone is on.');
    await expect(page.getByRole('region', { name: 'Unsaved changes' })).toHaveCount(0);

    await page.reload();
    await expect(highContrast).toHaveAttribute('aria-checked', 'false', { timeout: 15_000 });
    await expect(html(page)).not.toHaveClass(/\bhigh-contrast\b/);

    // It holds away from Settings too: App applies it on every route.
    await page.goto('/about');
    await expect(html(page)).not.toHaveClass(/\bhigh-contrast\b/);
    await page.goBack();

    await thisDevice(page).getByRole('button', { name: 'Use the default' }).click();
    await expect(html(page)).toHaveClass(/\bhigh-contrast\b/);
    await expect(thisDevice(page).locator('#setting-high-contrast-source')).toHaveText('Follows the default for everyone (on)');
    expect(await page.evaluate(() => localStorage.getItem('accessibility_device'))).toBeNull();
    expect(writes).toEqual([]);
});

test('editing a default never hides this device\'s own choice, and previews the ones it follows', async ({ page }) => {
    await openDisplay(page, { accessibility_reduced_motion: false });
    await thisDevice(page).getByRole('switch', { name: 'Reduced motion' }).click();
    await expect(html(page)).toHaveClass(/\breduced-motion\b/);

    const toggle = page.locator('[data-settings-more] > h3 > button');
    await toggle.click();
    const reducedMotionDefault = page.locator('[data-settings-more-body]').getByRole('switch', { name: 'Defaults for everyone Reduced motion' });
    // The default goes on and off again: this device made its own choice, so it keeps it throughout.
    await reducedMotionDefault.click();
    await expect(page.getByRole('region', { name: 'Unsaved changes' })).toBeVisible();
    await reducedMotionDefault.click();
    await expect(page.getByRole('region', { name: 'Unsaved changes' })).toHaveCount(0);
    await expect(html(page)).toHaveClass(/\breduced-motion\b/);
    await expect(thisDevice(page).locator('#setting-reduced-motion-source')).toHaveText('Set on this device. The default for everyone is off.');

    // High contrast follows the default here, so editing the default previews it at once.
    await page.locator('[data-settings-more-body]').getByRole('switch', { name: 'Defaults for everyone High contrast' }).click();
    await expect(html(page)).toHaveClass(/\bhigh-contrast\b/);
});

test('"Use the default" hands focus to its row\'s switch, which says it follows the default', async ({ page }) => {
    await openDisplay(page, { accessibility_high_contrast: false });
    const highContrast = thisDevice(page).getByRole('switch', { name: 'High contrast' });
    await highContrast.click();
    const useDefault = thisDevice(page).getByRole('button', { name: 'Use the default: High contrast' });
    await useDefault.focus();
    await page.keyboard.press('Enter');
    await expect(highContrast).toBeFocused();
    await expect(useDefault).toHaveCount(0);
    await expect(thisDevice(page).locator('#setting-high-contrast-source')).toHaveText('Follows the default for everyone (off)');
});

test('an unsaved default is previewed only while it is pending: Discard and leaving Settings end it, closing More options does not', async ({ page }) => {
    await openDisplay(page, { accessibility_high_contrast: false });
    const more = page.locator('[data-settings-more] > h3 > button');
    await more.click();
    const highContrastDefault = page.locator('[data-settings-more-body]').getByRole('switch', { name: 'Defaults for everyone High contrast' });
    await highContrastDefault.click();
    await expect(html(page)).toHaveClass(/\bhigh-contrast\b/);
    // The device card says what it shows, and that it is not saved yet.
    await expect(thisDevice(page).getByRole('switch', { name: 'High contrast' })).toHaveAttribute('aria-checked', 'true');
    await expect(thisDevice(page).locator('#setting-high-contrast-source')).toHaveText('Previewing the unsaved default for everyone (on)');

    // Closing More options leaves the draft pending, so the preview stays with it.
    await more.click();
    await expect(html(page)).toHaveClass(/\bhigh-contrast\b/);

    await page.getByRole('region', { name: 'Unsaved changes' }).getByRole('button', { name: 'Discard changes', exact: true }).click();
    await expect(html(page)).not.toHaveClass(/\bhigh-contrast\b/);
    await expect(thisDevice(page).locator('#setting-high-contrast-source')).toHaveText('Follows the default for everyone (off)');

    await more.click();
    await highContrastDefault.click();
    await expect(html(page)).toHaveClass(/\bhigh-contrast\b/);
    // Leaving with a change pending asks first; leaving without saving ends the preview everywhere.
    await page.getByText('About', { exact: true }).first().click();
    const leave = page.getByRole('alertdialog');
    if (await leave.isVisible().catch(() => false)) {
        await leave.getByRole('button', { name: /leave|discard/i }).first().click();
    }
    await expect(page).toHaveURL(/\/about/);
    await expect(html(page)).not.toHaveClass(/\bhigh-contrast\b/);
});

test('a device that chose high contrast paints it first, before the interface has loaded', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('accessibility_device', JSON.stringify({ highContrast: true, reducedMotion: true })));
    // Hold the interface's language back, so what shows is the boot script's first paint alone.
    await page.route(/\/src\/lib\/i18n\/locales\/en/, () => undefined);
    await page.goto('/about', { waitUntil: 'domcontentloaded' });
    await expect(html(page)).toHaveClass(/(?=.*\bhigh-contrast\b)(?=.*\bdark\b)(?=.*\breduced-motion\b)/);
    await expect(page.locator('#app')).toBeEmpty();
});
