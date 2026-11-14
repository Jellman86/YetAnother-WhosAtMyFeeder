import { expect, test, type Page } from '@playwright/test';
import { openSettings, saveBar } from './settings-page-mock';

// Settings' shape: a compact rail beside the settings on a wide screen, one named select on a
// phone, every setting in one home, and Detection leading with its everyday decisions.

const rail = (page: Page) => page.locator('[data-settings-navigation]');

test.describe('on a wide screen', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('the sections are a rail beside the settings, so the first setting starts near the top', async ({ page }) => {
        await openSettings(page);
        await expect(rail(page)).toBeVisible();
        await expect(page.locator('#settings-tab-select')).toBeHidden();
        const railBox = await rail(page).boundingBox();
        const field = await page.locator('#frigate-url').boundingBox();
        expect(railBox && field).toBeTruthy();
        // The rail sits to the left of the settings, not above them.
        expect((field?.x ?? 0)).toBeGreaterThan((railBox?.x ?? 0) + (railBox?.width ?? 0));
        expect(field?.y ?? 1000).toBeLessThan(400);
        await expect(rail(page).getByRole('link', { name: 'Connection', exact: true })).toHaveAttribute('aria-current', 'page');
        await expect(rail(page).getByRole('link', { name: 'Enrichment' })).toHaveCount(0);
        const wizard = rail(page).getByRole('button', { name: 'Setup wizard', exact: true });
        expect((await wizard.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
    });

    test('a skip link moves keyboard focus past the rail to the settings', async ({ page }) => {
        await openSettings(page);
        const skip = page.locator('[data-settings-skip-link]');
        await skip.focus();
        await expect(skip).toBeVisible();
        await page.keyboard.press('Enter');
        await expect(page.locator('#settings-content')).toBeFocused();
        await page.keyboard.press('Tab');
        const focusedInRail = await page.evaluate(() => Boolean(document.activeElement?.closest('[data-settings-navigation]')));
        expect(focusedInRail).toBe(false);
    });

    test('a section with unsaved changes is marked in words in the rail', async ({ page }) => {
        await openSettings(page);
        await page.locator('#mqtt-server').fill('broker.lan');
        await expect(rail(page).getByRole('link', { name: 'Connection', exact: true })).toContainText('unsaved');
        await expect(rail(page).getByRole('link', { name: 'Detection', exact: true })).not.toContainText('unsaved');
    });

    test('telemetry lives with Data, and Integrations ends with the species information sources', async ({ page }) => {
        await openSettings(page, { ebird_enabled: false, enrichment_sightings_source: 'disabled' });
        await expect(page.getByText('Anonymous usage', { exact: false }).first()).toHaveCount(0);
        await rail(page).getByRole('link', { name: 'Data', exact: true }).click();
        await expect(page.getByRole('switch', { name: /telemetry/i }).first()).toBeVisible();

        await rail(page).getByRole('link', { name: 'Integrations', exact: true }).click();
        const sources = page.locator('[data-enrichment-summary]');
        await expect(sources).toContainText('Not shown: needs an eBird API key');
        await page.getByRole('button', { name: 'Set up eBird', exact: true }).click();
        await expect(page.locator('[aria-labelledby="setting-ebird-enabled"]')).toBeFocused();
        await expect(saveBar(page)).toHaveCount(0);
    });

    test('Detection leads with the confidence sliders; Hardware and Frigate options start closed', async ({ page }) => {
        await openSettings(page);
        await rail(page).getByRole('link', { name: 'Detection', exact: true }).click();
        const slider = page.locator('#confidence-threshold-slider');
        await expect(slider).toBeVisible();
        const hardware = page.getByRole('button', { name: 'Hardware', exact: true });
        const frigate = page.getByRole('button', { name: 'Frigate and video', exact: true });
        await expect(hardware).toHaveAttribute('aria-expanded', 'false');
        await expect(frigate).toHaveAttribute('aria-expanded', 'false');
        const sliderBox = await slider.boundingBox();
        const hardwareBox = await hardware.boundingBox();
        expect((sliderBox?.y ?? 0)).toBeLessThan(hardwareBox?.y ?? 0);
        await frigate.click();
        await expect(frigate).toHaveAttribute('aria-expanded', 'true');
        await expect(page.getByRole('switch', { name: /Frigate/ }).first()).toBeVisible();
    });
});

test.describe('on a phone', () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test('one select names the current section, and the setup wizard is an ordinary button', async ({ page }) => {
        await openSettings(page);
        await expect(rail(page)).toBeHidden();
        const select = page.getByRole('combobox', { name: 'Settings section', exact: true });
        await expect(select).toBeVisible();
        await expect(select).toHaveValue('connection');
        await select.selectOption('detection');
        await expect(page.locator('#confidence-threshold-slider')).toBeVisible();
        const wizard = page.getByRole('button', { name: 'Setup wizard', exact: true });
        expect((await wizard.boundingBox())?.height ?? 0).toBeGreaterThanOrEqual(44);
        const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
        expect(overflow).toBeLessThanOrEqual(1);
    });
});
