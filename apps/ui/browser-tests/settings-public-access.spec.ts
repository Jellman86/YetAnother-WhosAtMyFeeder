import { expect, test } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// Public access only means something once sign-in is on. With sign-in off it cannot be turned on,
// and says why; but an install where it is already on can always turn it off.

test('with sign-in off, public access cannot be turned on and says why', async ({ page }) => {
    await openSettings(page, { auth_enabled: false, public_access_enabled: false });
    await page.getByRole('link', { name: 'Access & privacy', exact: true }).click();
    const publicAccess = page.getByRole('switch', { name: 'Public access' });
    await expect(publicAccess).toHaveAttribute('aria-checked', 'false');
    await expect(publicAccess).toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('[data-public-needs-auth]')).toBeVisible();
});

test('with sign-in off, public access that is on can still be turned off, and then not back on', async ({ page }) => {
    const harness = await openSettings(page, { auth_enabled: false, public_access_enabled: true });
    await page.getByRole('link', { name: 'Access & privacy', exact: true }).click();
    const publicAccess = page.getByRole('switch', { name: 'Public access' });
    await expect(publicAccess).toHaveAttribute('aria-checked', 'true');
    await expect(publicAccess).not.toHaveAttribute('aria-disabled', 'true');
    await expect(page.locator('[data-public-needs-auth]')).toBeVisible();

    await publicAccess.click();
    await expect(publicAccess).toHaveAttribute('aria-checked', 'false');
    await expect(publicAccess).toHaveAttribute('aria-disabled', 'true');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0].public_access_enabled).toBe(false);
});
