import { expect, test, type Page } from '@playwright/test';
import { openMoreOptions, openSettings, saveBar as unsavedChanges } from './settings-page-mock';

// Settings → Display: the defaults for everyone, under More options, are in the one Settings
// draft and save with the rest of the form. This device's own choices are in
// settings-accessibility-device.spec.ts.
const defaults = (page: Page) => page.locator('[data-settings-more-body]');
const thisDevice = (page: Page) => page.locator('[data-settings-part="accessibility"]');

test('the defaults for everyone load on first open, keep an edit across sections and save with Apply', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const harness = await openSettings(page, {
        accessibility_high_contrast: true,
        accessibility_live_announcements: false
    });
    expect(harness.moduleRequests('AccessibilitySettings.svelte')).toBe(0);

    await page.getByRole('link', { name: 'Display', exact: true }).click();
    await expect(thisDevice(page).getByRole('switch', { name: 'High contrast' })).toHaveAttribute('aria-checked', 'true');
    expect(harness.moduleRequests('AccessibilitySettings.svelte')).toBe(1);
    await openMoreOptions(page);
    const highContrast = defaults(page).getByRole('switch', { name: 'Defaults for everyone High contrast' });
    const reducedMotion = defaults(page).getByRole('switch', { name: 'Defaults for everyone Reduced motion' });
    const announcements = defaults(page).getByRole('switch', { name: 'Defaults for everyone Live announcements' });
    await expect(highContrast).toHaveAttribute('aria-checked', 'true');
    await expect(reducedMotion).toHaveAttribute('aria-checked', 'false');
    await expect(announcements).toHaveAttribute('aria-checked', 'false');
    await expect(unsavedChanges(page)).toHaveCount(0);

    await reducedMotion.click();
    await expect(reducedMotion).toHaveAttribute('aria-checked', 'true');
    await expect(unsavedChanges(page)).toBeVisible();

    await page.getByRole('link', { name: 'Cameras & connection', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toBeVisible();
    await page.getByRole('link', { name: 'Display', exact: true }).click();
    await expect(reducedMotion).toHaveAttribute('aria-checked', 'true');

    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({
        accessibility_high_contrast: true,
        accessibility_dyslexia_font: false,
        accessibility_live_announcements: false,
        accessibility_reduced_motion: true
    });
    await expect(unsavedChanges(page)).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('turning a default back to its saved value leaves nothing to apply', async ({ page }) => {
    await openSettings(page);
    await page.getByRole('link', { name: 'Display', exact: true }).click();
    await openMoreOptions(page);
    const announcements = defaults(page).getByRole('switch', { name: 'Live announcements' });
    await expect(announcements).toHaveAttribute('aria-checked', 'true');
    await announcements.click();
    await expect(unsavedChanges(page)).toBeVisible();
    await announcements.click();
    await expect(unsavedChanges(page)).toHaveCount(0);
});
