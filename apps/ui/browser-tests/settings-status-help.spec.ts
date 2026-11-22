import { expect, test, type Page } from '@playwright/test';
import { HEALTHY_CONNECTIONS, replayFeeder, settled } from './accessibility-mock';

/**
 * The status column beside the settings says what each connection is for and its cause in words,
 * never a raw code. YA-WAMF keeps no test result, so a result is shown only for a test run during
 * this visit, with its time; otherwise the column says so and offers the test. Every test here
 * fails on a page error, so a section's runner that loops cannot pass unseen.
 */
const column = (page: Page) => page.locator('[data-settings-section-status="side"]');
const item = (page: Page, key: string) => column(page).locator(`[data-section-status-item="${key}"]`);
const TIME = '\\d{1,2}:\\d{2}(?::\\d{2})?(?:\\s?[AP]M)?';

async function openSection(page: Page, path: string): Promise<string[]> {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await replayFeeder(page, 'light', { '/api/diagnostics/connections': HEALTHY_CONNECTIONS });
    // Frigate answers the connection test; the broker publish is refused by the read-only fixture.
    await page.route((url) => url.pathname === '/api/frigate/test', (route) => route.fulfill({ json: { status: 'ok', version: '0.14.1' } }));
    await page.goto(path);
    // The column beside the settings from a wide window, above them on a phone: either shows the chips.
    await expect(page.locator('[data-section-status-item]:visible').first()).toBeVisible({ timeout: 15_000 });
    await settled(page);
    return errors;
}

async function closeTestDialog(page: Page): Promise<void> {
    const dialog = page.getByRole('dialog');
    await expect(dialog).toBeVisible();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
}

test.describe('beside the settings', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('each connection says what it is for and its cause in words, with no raw code', async ({ page }) => {
        const errors = await openSection(page, '/settings/cameras');
        const frigate = item(page, 'frigate');
        await expect(frigate.locator('[data-section-status-purpose]')).toHaveText('Frigate records the cameras. YA-WAMF reads each visit\'s photos and video from it.');
        await expect(frigate.locator('[data-section-status-cause]')).toHaveText('Frigate answers, and no camera is reported offline.');
        await expect(item(page, 'mqtt').locator('[data-section-status-cause]')).toHaveText('Connected to the broker.');
        await expect(column(page).locator('[title]')).toHaveCount(0);
        await expect(column(page)).not.toContainText('reachable');
        expect(errors).toEqual([]);
    });

    test('says no result is kept until the test runs, then the result of this visit with its time', async ({ page }) => {
        const errors = await openSection(page, '/settings/cameras');
        const frigateTest = item(page, 'frigate').locator('[data-section-status-test]');
        const mqttTest = item(page, 'mqtt').locator('[data-section-status-test]');
        await expect(frigateTest).toHaveText('Test results aren\'t kept. Run the test to check now.');
        await expect(frigateTest).toHaveAttribute('data-section-status-test', 'not-kept');

        await item(page, 'frigate').getByRole('button', { name: 'Run the test: Frigate' }).click();
        await expect(frigateTest).toHaveAttribute('data-section-status-test', 'this-visit', { timeout: 15_000 });
        await expect(frigateTest).toHaveText(new RegExp(`^Tested at ${TIME}: it worked\\.$`));
        // One run tests both connections, each with its own outcome.
        await expect(mqttTest).toHaveText(new RegExp(`^Tested at ${TIME}: it did not work\\. Run it again to see why\\.$`));
        await closeTestDialog(page);

        // A reload forgets it: nothing is kept.
        await page.reload();
        await expect(frigateTest).toHaveAttribute('data-section-status-test', 'not-kept', { timeout: 15_000 });
        expect(errors).toEqual([]);
    });

    test('says when a test ran with values not saved yet, and drops the result at the next edit', async ({ page }) => {
        const errors = await openSection(page, '/settings/cameras');
        const frigateTest = item(page, 'frigate').locator('[data-section-status-test]');
        await page.locator('#frigate-url').fill('http://frigate.example:5000');
        await item(page, 'frigate').getByRole('button', { name: 'Run the test: Frigate' }).click();
        await expect(frigateTest).toHaveAttribute('data-section-status-test', 'this-visit-unsaved', { timeout: 15_000 });
        await expect(frigateTest).toHaveText(new RegExp(`^Tested at ${TIME} with the values on this page, not saved yet: it worked\\.$`));
        await closeTestDialog(page);

        // The result described values that are no longer on the page.
        await page.locator('#frigate-url').fill('http://frigate.example:5001');
        await expect(frigateTest).toHaveAttribute('data-section-status-test', 'not-kept');
        expect(errors).toEqual([]);
    });

    test('offers BirdNET-Go\'s test from the column in Integrations, with no page error', async ({ page }) => {
        const errors = await openSection(page, '/settings/integrations');
        const audio = item(page, 'audio');
        // BirdNET-Go is on the section's first screen, so its test is offered from the column once
        // its code has arrived; switching audio off and on again withdraws and offers it again.
        await expect(audio.getByRole('button', { name: 'Run the test: BirdNET-Go' })).toBeVisible();
        const audioSwitch = page.locator('[data-settings-part="birdnet"] button[aria-checked]').first();
        await audioSwitch.click();
        await expect(audio.getByRole('button', { name: 'Go to the test: BirdNET-Go' })).toBeVisible();
        await audioSwitch.click();
        await expect(audio.getByRole('button', { name: 'Run the test: BirdNET-Go' })).toBeVisible();
        expect(errors).toEqual([]);
    });

    test('goes to the BirdNET-Go switch when audio is off on this page, so focus always moves on', async ({ page }) => {
        const errors = await openSection(page, '/settings/integrations');
        const audioSwitch = page.locator('[data-settings-part="birdnet"] button[aria-checked]').first();
        await audioSwitch.click();
        await item(page, 'audio').getByRole('button', { name: 'Go to the test: BirdNET-Go' }).click();
        await expect(audioSwitch).toBeFocused();
        expect(errors).toEqual([]);
    });
});

test.describe('above the settings on a phone', () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test('stays short: the chips, and words only for what needs a look', async ({ page }) => {
        const errors = await openSection(page, '/settings/cameras');
        const top = page.locator('[data-settings-section-status="top"]');
        await expect(top.locator('[data-section-status-item="frigate"]')).toBeVisible();
        await expect(top.locator('[data-section-status-purpose]')).toHaveCount(0);
        await expect(top.locator('[data-section-status-test]')).toHaveCount(0);
        await expect(top.locator('[data-section-status-item="frigate"] [data-section-status-cause]')).toHaveCount(0);
        expect(errors).toEqual([]);
    });
});
