import { test, expect, type Page } from '@playwright/test';
import { openDetectionSettings } from './detection-settings-mock';

const unsaved = (page: Page) => page.getByText('Unsaved Changes', { exact: true });
const finder = (page: Page) => page.getByRole('group', { name: 'Bird finder' });

test('the bird finder choice waits for Apply Settings and saves with the rest of the form', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', error => errors.push(error.message));
    const state = await openDetectionSettings(page);
    const standard = finder(page).getByRole('radio', { name: /Standard \(YOLOX-Tiny\)/ });
    const wide = finder(page).getByRole('radio', { name: /Wide frame \(RF-DETR Nano\)/ });
    await expect(standard).toBeChecked();
    await expect(unsaved(page)).toHaveCount(0);

    await wide.check();
    await expect(wide).toBeChecked();
    await expect(unsaved(page)).toBeVisible();
    await expect(finder(page)).toContainText('Apply settings to switch');
    expect(state.saves).toEqual([]);

    await page.locator('#confidence-threshold-slider').fill('0.75');
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].bird_crop_accurate_detector).toBe('rfdetr_nano');
    expect(state.saves[0].classification_threshold).toBe(0.75);
    await expect(unsaved(page)).toHaveCount(0);
    await expect(wide).toBeChecked();
    await expect(finder(page)).not.toContainText('Apply settings to switch');
    expect(errors).toEqual([]);
});

test('an unchanged form still sends the saved finder, so an unrelated save never resets it', async ({ page }) => {
    const state = await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    await expect(finder(page).getByRole('radio', { name: /Wide frame/ })).toBeChecked();
    await page.locator('#confidence-threshold-slider').fill('0.65');
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].bird_crop_accurate_detector).toBe('rfdetr_nano');
});

test('a failed save keeps the staged finder and says the settings were not saved', async ({ page }) => {
    const state = await openDetectionSettings(page, { saveFails: true });
    const wide = finder(page).getByRole('radio', { name: /Wide frame/ });
    await wide.check();
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect(page.getByRole('status').filter({ hasText: 'Settings store unavailable' }).first()).toBeVisible();
    await expect(wide).toBeChecked();
    await expect(unsaved(page)).toBeVisible();
    expect(state.saves).toEqual([]);
});

test('a chosen finder that is not downloaded is explained and offers the download', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', rfdetrInstalled: false });
    await expect(finder(page)).toContainText('not downloaded yet');
    await expect(finder(page).getByRole('button', { name: 'Download RF-DETR Nano' })).toBeVisible();
});

test('each finder states its device on this host without claiming an unchecked accelerator', async ({ page }) => {
    await openDetectionSettings(page);
    const standard = page.locator('label').filter({ has: page.getByRole('radio', { name: /Standard/ }) });
    const wide = page.locator('label').filter({ has: page.getByRole('radio', { name: /Wide frame/ }) });
    await expect(wide).toContainText('Runs on Intel GPU (OpenVINO), passed the device check on this host');
    await expect(standard).toContainText('Runs on the CPU. No current device check on this host for this finder.');
    await expect(standard).not.toContainText('passed the device check');
    await expect(finder(page)).toContainText('19.3 MB download · ~512 MB RAM');
    await expect(finder(page)).toContainText('102.8 MB download');
});

test('a saved provider this host cannot use is flagged in words beside the choice', async ({ page }) => {
    await openDetectionSettings(page, { savedProvider: 'cuda' });
    const provider = page.locator('#inference-provider');
    await expect(provider).toHaveValue('cuda');
    await expect(page.getByRole('status').filter({ hasText: 'NVIDIA CUDA is saved but is not available' })).toBeVisible();
    await expect(provider.locator('option[value="cuda"]')).toBeDisabled();
});

test('memory and isolation open from the keyboard and keep their values through a save', async ({ page }) => {
    const state = await openDetectionSettings(page);
    const disclosure = page.getByRole('button', { name: /Memory and isolation/ });
    await expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    await expect(page.locator('#image-execution-mode')).toHaveCount(0);
    await disclosure.focus();
    await page.keyboard.press('Enter');
    await expect(disclosure).toHaveAttribute('aria-expanded', 'true');
    await page.locator('#live-worker-count').fill('2');
    await expect(unsaved(page)).toBeVisible();
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].live_worker_count).toBe(2);
    expect(state.saves[0].image_execution_mode).toBe('subprocess');
});

for (const width of [320, 393]) {
    test(`the Detection tab reflows at ${width}px with 200% text`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await openDetectionSettings(page);
        await page.addStyleTag({ content: 'html{font-size:200%!important}' });
        await expect(page.locator('#confidence-threshold-slider')).toBeVisible();
        await page.getByRole('button', { name: /Memory and isolation/ }).click();
        await expect(page.locator('#live-worker-count')).toBeVisible();
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
        // Cards clip their content, so a page without a scrollbar can still hide words.
        const clipped = await page.evaluate(() => [...document.querySelectorAll('section.card-base *')]
            .filter((element) => {
                const box = element.getBoundingClientRect();
                return box.width > 0 && box.right > window.innerWidth + 1;
            })
            .map((element) => (element.textContent ?? '').trim().slice(0, 40)));
        expect(clipped).toEqual([]);
        const wide = finder(page).getByRole('radio', { name: /Wide frame/ });
        await wide.focus();
        await page.keyboard.press('Space');
        await expect(wide).toBeChecked();
        await expect(unsaved(page)).toBeVisible();
    });
}
