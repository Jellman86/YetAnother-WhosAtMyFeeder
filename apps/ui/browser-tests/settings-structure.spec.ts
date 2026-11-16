import { expect, test, type Page } from '@playwright/test';
import { openSettings, saveBar } from './settings-page-mock';
import { openDetectionSettings } from './detection-settings-mock';

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

    test('telemetry lives with Security, and Integrations ends with the species information sources', async ({ page }) => {
        await openSettings(page, { ebird_enabled: false, enrichment_sightings_source: 'disabled' });
        await expect(page.getByText('Anonymous usage', { exact: false }).first()).toHaveCount(0);
        await rail(page).getByRole('link', { name: 'Security', exact: true }).click();
        await expect(page.getByRole('switch', { name: /telemetry/i }).first()).toBeVisible();

        await rail(page).getByRole('link', { name: 'Integrations', exact: true }).click();
        const sources = page.locator('[data-enrichment-summary]');
        await expect(sources).toContainText('Not shown: needs an eBird API key');
        // The summary links to eBird's own switch rather than offering a second way to turn it on.
        await page.getByRole('button', { name: 'Go to eBird', exact: true }).click();
        await expect(page.getByRole('switch', { name: 'eBird' })).toBeFocused();
        await expect(saveBar(page)).toHaveCount(0);
    });

    test('Detection leads with the confidence sliders, and the models and hardware are their own tab', async ({ page }) => {
        await openSettings(page);
        await rail(page).getByRole('link', { name: 'Detection', exact: true }).click();
        const slider = page.locator('#confidence-threshold-slider');
        await expect(slider).toBeVisible();
        const frigate = page.getByRole('button', { name: 'Frigate and video', exact: true });
        await expect(frigate).toHaveAttribute('aria-expanded', 'false');
        await expect(page.getByRole('button', { name: 'Hardware', exact: true })).toHaveCount(0);
        await frigate.click();
        await expect(frigate).toHaveAttribute('aria-expanded', 'true');
        await expect(page.getByRole('switch', { name: /Frigate/ }).first()).toBeVisible();

        await page.getByRole('button', { name: 'Open Models', exact: true }).click();
        await expect(rail(page).getByRole('link', { name: 'Models', exact: true })).toHaveAttribute('aria-current', 'page');
        // Hardware is a plain section like every other: its device choice is on the surface.
        await expect(page.getByRole('heading', { name: 'Hardware', exact: true })).toBeVisible();
        await expect(page.locator('#inference-provider')).toBeVisible();
        await expect(page.locator('#bird-model-region-override')).toBeVisible();
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

test.describe('a refused value inside a closed card', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('opens the cards that hold it and focuses it, after visiting the tab and leaving it', async ({ page }) => {
        await openSettings(page, { auto_video_classification: true, video_classification_delay: 30 }, {
            refuseWrite: () => ({
                status: 422,
                json: { detail: [{ type: 'less_than_equal', loc: ['body', 'video_classification_delay'], msg: 'Input should be less than or equal to 3600', ctx: { le: 3600 } }] }
            })
        });
        await rail(page).getByRole('link', { name: 'Detection', exact: true }).click();
        await expect(page.getByRole('button', { name: 'Frigate and video', exact: true })).toHaveAttribute('aria-expanded', 'false');
        await rail(page).getByRole('link', { name: 'Connection', exact: true }).click();
        await page.locator('#mqtt-server').fill('broker.lan');
        await page.getByRole('button', { name: 'Save changes', exact: true }).click();

        await expect(rail(page).getByRole('link', { name: 'Detection', exact: true })).toHaveAttribute('aria-current', 'page');
        await expect(page.getByRole('button', { name: 'Frigate and video', exact: true })).toHaveAttribute('aria-expanded', 'true');
        const delay = page.locator('#video-delay');
        await expect(delay).toBeFocused();
        await expect(delay).toHaveAttribute('aria-invalid', 'true');
    });

    test('opens the memory section for a refused worker count', async ({ page }) => {
        await openSettings(page, {}, {
            refuseWrite: () => ({
                status: 422,
                json: { detail: [{ type: 'less_than_equal', loc: ['body', 'live_worker_count'], msg: 'Input should be less than or equal to 8', ctx: { le: 8 } }] }
            })
        });
        await page.locator('#mqtt-server').fill('broker.lan');
        await page.getByRole('button', { name: 'Save changes', exact: true }).click();
        await expect(page.getByRole('button', { name: /Memory and isolation/ })).toHaveAttribute('aria-expanded', 'true');
        await expect(page.locator('#live-worker-count')).toBeFocused();
    });
});

test.describe('a refused value inside a closed card', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('opens Maintenance at Jobs at once for a refused concurrency, and focuses the field', async ({ page }) => {
        await openSettings(page, {}, {
            refuseWrite: () => ({
                status: 422,
                json: { detail: [{ type: 'less_than_equal', loc: ['body', 'maintenance_max_concurrent'], msg: 'Input should be less than or equal to 8', ctx: { le: 8 } }] }
            })
        });
        await page.locator('#mqtt-server').fill('broker.lan');
        await page.getByRole('button', { name: 'Save changes', exact: true }).click();
        await expect(rail(page).getByRole('link', { name: 'Maintenance', exact: true })).toHaveAttribute('aria-current', 'page');
        await expect(page.getByRole('heading', { name: 'Jobs at once', exact: true })).toBeVisible();
        await expect(page.locator('#maintenance-max-concurrent')).toBeFocused();
    });
});

test.describe('the runtime report, after it was closed and the tab left', () => {
    test.use({ viewport: { width: 1440, height: 900 } });
    const report = (page: Page) => page.getByRole('button', { name: /Runtime report/ });
    const reportLink = (page: Page) => page.getByRole('button', { name: /to check in the runtime report/ });

    async function closeReportAndReturn(page: Page): Promise<void> {
        if ((await report(page).getAttribute('aria-expanded')) === 'false') await report(page).click();
        await report(page).click();
        await expect(report(page)).toHaveAttribute('aria-expanded', 'false');
        await rail(page).getByRole('link', { name: 'Connection', exact: true }).click();
        await expect(page.locator('#mqtt-server')).toBeVisible();
        await rail(page).getByRole('link', { name: 'Models', exact: true }).click();
    }

    test('with nothing to check, the status line has no report link', async ({ page }) => {
        await openDetectionSettings(page);
        await expect(page.locator('[data-identification-status]')).toBeVisible();
        await expect(reportLink(page)).toHaveCount(0);
    });

    test('a runtime problem opens the report; once closed on it, the same problem keeps it closed on return', async ({ page }) => {
        await openDetectionSettings(page, { statusExtra: { fallback_reason: 'Intel GPU failed to compile the model' } });
        // The problem arrives with the runtime status, after the page itself: the status line says
        // the chosen device failed, and the report opens with the raw reason in it.
        await expect(page.locator('[data-identification-status]')).toContainText('because the chosen device failed its check');
        await expect(report(page)).toHaveAttribute('aria-expanded', 'true');
        await expect(page.locator('#detection-runtime-report')).toContainText('Intel GPU failed to compile the model');
        await closeReportAndReturn(page);
        await expect(report(page)).toHaveAttribute('aria-expanded', 'false');
        // The status line's link still opens it, whatever was remembered.
        await reportLink(page).click();
        await expect(report(page)).toHaveAttribute('aria-expanded', 'true');
        await expect(page.locator('#detection-runtime-report')).toBeInViewport();
    });
});
