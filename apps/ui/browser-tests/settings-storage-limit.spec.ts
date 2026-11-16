import { test, expect } from '@playwright/test';
import { openSettings, saveBar, saveButton } from './settings-page-mock';

// An emptied storage limit must never be saved as a small one: the page refuses the save and says
// which field to fix, and the saved limit is what stays in the form meanwhile.
test.use({ viewport: { width: 1440, height: 900 } });

test('an emptied storage limit blocks the save instead of saving a small limit', async ({ page }) => {
    const harness = await openSettings(page, { media_cache_max_size_mb: 20480 });
    await page.locator('#mqtt-server').fill('broker.lan');
    await page.getByRole('link', { name: 'Data', exact: true }).click();
    const limit = page.getByRole('spinbutton', { name: /^Storage limit in GB/ });
    await expect(limit).toHaveValue('20');
    await limit.fill('');
    await limit.blur();
    await expect(limit).toHaveAttribute('aria-invalid', 'true');

    await saveButton(page).click();
    await expect(saveBar(page).locator('[data-save-problem]')).toContainText('Nothing was saved');
    expect(harness.writes).toEqual([]);

    await limit.fill('25');
    await limit.blur();
    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({ media_cache_max_size_mb: 25600, mqtt_server: 'broker.lan' });
});
