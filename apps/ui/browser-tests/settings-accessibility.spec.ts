import { expect, test } from '@playwright/test';
import { openSettings, unsavedChanges } from './settings-page-mock';

// Settings → Accessibility keeps its toggles in the one Settings draft and loads its tab body on
// first use; Apply saves them with the rest of the form.

test('Accessibility loads on first open, keeps an edit across tabs and saves it with Apply', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const harness = await openSettings(page, {
        accessibility_high_contrast: true,
        accessibility_live_announcements: false
    });
    expect(harness.moduleRequests('AccessibilitySettings.svelte')).toBe(0);

    await page.getByRole('link', { name: 'Accessibility' }).click();
    const highContrast = page.getByRole('switch', { name: 'High Contrast' });
    const reducedMotion = page.getByRole('switch', { name: 'Reduced Motion' });
    const announcements = page.getByRole('switch', { name: 'Live announcements' });
    await expect(highContrast).toHaveAttribute('aria-checked', 'true');
    expect(harness.moduleRequests('AccessibilitySettings.svelte')).toBe(1);
    await expect(reducedMotion).toHaveAttribute('aria-checked', 'false');
    await expect(announcements).toHaveAttribute('aria-checked', 'false');
    await expect(unsavedChanges(page)).toHaveCount(0);

    await reducedMotion.click();
    await expect(reducedMotion).toHaveAttribute('aria-checked', 'true');
    await expect(unsavedChanges(page)).toBeVisible();

    await page.getByRole('link', { name: 'Connection' }).click();
    await expect(page.locator('#mqtt-server')).toBeVisible();
    await page.getByRole('link', { name: 'Accessibility' }).click();
    await expect(reducedMotion).toHaveAttribute('aria-checked', 'true');

    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
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

test('turning a toggle back to its saved value leaves nothing to apply', async ({ page }) => {
    await openSettings(page);
    await page.getByRole('link', { name: 'Accessibility' }).click();
    const announcements = page.getByRole('switch', { name: 'Live announcements' });
    await expect(announcements).toHaveAttribute('aria-checked', 'true');
    await announcements.click();
    await expect(unsavedChanges(page)).toBeVisible();
    await announcements.click();
    await expect(unsavedChanges(page)).toHaveCount(0);
});
