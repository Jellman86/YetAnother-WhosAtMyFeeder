import { expect, test } from '@playwright/test';
import { openSettings, saveBar as unsaved, type FixtureSettings } from './settings-page-mock';

// Settings → Display holds its choices in the one Settings draft and loads its tab body on
// first use. The saved choices must load into the tab, an edit must survive leaving the tab, and
// Apply must send the Appearance fields with the rest of the form.

const SAVED_APPEARANCE: FixtureSettings = {
    display_common_names: true,
    scientific_name_primary: true,
    appearance_explorer_view: 'list',
    date_format: 'ymd',
    time_format: '12h',
    appearance_font_theme: 'studio',
    appearance_color_theme: 'default'
};

test('Appearance loads on first open, shows the saved choices and saves edits with Apply', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const harness = await openSettings(page, SAVED_APPEARANCE);
    expect(harness.moduleRequests('AppearanceSettings.svelte')).toBe(0);

    await page.getByRole('link', { name: 'Display', exact: true }).click();
    await expect(page.locator('#date-format-select')).toHaveValue('ymd');
    expect(harness.moduleRequests('AppearanceSettings.svelte')).toBe(1);
    await expect(page.locator('#time-format-select')).toHaveValue('12h');
    await expect(page.locator('#explorer-view-select')).toHaveValue('list');
    await expect(page.getByRole('radiogroup', { name: /Bird naming style/ }).getByRole('radio', { name: /^Scientific name first/ })).toBeChecked();
    await expect(unsaved(page)).toHaveCount(0);

    await page.locator('#time-format-select').selectOption('24h');
    await page.getByRole('button', { name: /advanced options/i }).click();
    await page.getByRole('radiogroup', { name: /Colou?r accent/i }).getByRole('radio', { name: /^Blue Tit/ }).check();
    await expect(unsaved(page)).toBeVisible();

    // Leaving the tab unmounts its body; the draft is the page's, so the edit is still there.
    await page.getByRole('link', { name: 'Cameras & connection', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toBeVisible();
    await expect(unsaved(page)).toBeVisible();
    await page.getByRole('link', { name: 'Display', exact: true }).click();
    await expect(page.locator('#time-format-select')).toHaveValue('24h');

    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0]).toMatchObject({
        ...SAVED_APPEARANCE,
        time_format: '24h',
        appearance_color_theme: 'bluetit'
    });
    await expect(unsaved(page)).toHaveCount(0);
    await expect(page.locator('#time-format-select')).toHaveValue('24h');
    expect(errors).toEqual([]);
});

test('switching the naming style back to the saved one leaves nothing to apply', async ({ page }) => {
    await openSettings(page, SAVED_APPEARANCE);
    await page.getByRole('link', { name: 'Display', exact: true }).click();
    const scientific = page.getByRole('radiogroup', { name: /Bird naming style/ }).getByRole('radio', { name: /^Strictly scientific/i });
    const hobbyist = page.getByRole('radiogroup', { name: /Bird naming style/ }).getByRole('radio', { name: /^Scientific name first/ });
    await expect(hobbyist).toBeChecked();

    await scientific.check();
    await expect(scientific).toBeChecked();
    await expect(unsaved(page)).toBeVisible();
    await hobbyist.check();
    await expect(unsaved(page)).toHaveCount(0);
});
