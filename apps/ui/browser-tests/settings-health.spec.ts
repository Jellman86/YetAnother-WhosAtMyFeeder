import { expect, test } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// Settings → Health is the diagnostics page shown as a tab. It loads only when opened, and a
// detection set aside elsewhere in Settings links straight to it.

test('Health loads on first open and keeps the form untouched', async ({ page }) => {
    const harness = await openSettings(page);
    expect(harness.moduleRequests('Errors.svelte')).toBe(0);

    await page.getByRole('link', { name: 'Health' }).click();
    await expect(page.locator('[data-fixture-route]')).toHaveAttribute('data-fixture-route', '/settings/health');
    await expect(page.locator('[data-health-timeline]')).toBeVisible();
    expect(harness.moduleRequests('Errors.svelte')).toBe(1);
    await expect(page.getByText('Unsaved Changes', { exact: true })).toHaveCount(0);

    await page.getByRole('link', { name: 'Connection' }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await page.getByRole('link', { name: 'Health' }).click();
    await expect(page.locator('[data-health-timeline]')).toBeVisible();
    expect(harness.moduleRequests('Errors.svelte')).toBe(1);
});
