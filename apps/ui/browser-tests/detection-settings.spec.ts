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
    await expect(wide).toContainText('Recommended: Intel GPU (OpenVINO). Passed the device check on this host.');
    // Unchecked here, so it says which devices it could use and that they need a check first.
    await expect(standard).toContainText('CPU until Intel GPU (OpenVINO) and Intel NPU (OpenVINO) pass a device check on this host.');
    await expect(standard).not.toContainText('passed the device check');
    await expect(finder(page)).toContainText('19.3 MB download · ~512 MB RAM');
    await expect(finder(page)).toContainText('102.8 MB download');
});

test('the chosen unchecked finder offers a device check scoped to it alone', async ({ page }) => {
    const runs: unknown[] = [];
    await openDetectionSettings(page);
    await page.route('**/api/diagnostics/model-eval/runs', route => {
        if (route.request().method() !== 'POST') return route.fallback();
        runs.push(route.request().postDataJSON());
        return route.fulfill({ json: { run_id: 'finder-check' } });
    });
    const check = finder(page).getByRole('button', { name: 'Check Intel GPU (OpenVINO) and Intel NPU (OpenVINO) for YOLOX-Tiny' });
    await expect(check).toBeVisible();
    await expect(finder(page)).toContainText('The identification model is not changed.');
    await check.click();
    await expect.poll(() => runs.length).toBe(1);
    // Scoped to the finder: no identification model is activated or downloaded for it.
    expect(runs[0]).toMatchObject({ sweep_devices: true, compat_only: true, sweep_all_models: false, model_ids: ['bird_crop_detector_accurate_yolox_tiny'] });
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


test('a checked finder keeps its scoped check and shows actual CPU fallback separately from its GPU recommendation', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', finderExecution: {
        model_id: 'bird_crop_detector_accurate_rfdetr_nano', provider: 'cpu', requested_provider: 'intel_gpu',
        devices: ['CPUExecutionProvider'], checked_at: '2026-10-25T08:00:00Z', fallback_reason: 'runtime_failed'
    } });
    await expect(finder(page)).toContainText('Recommended: Intel GPU (OpenVINO)');
    await expect(finder(page)).toContainText('Last completed run: CPU');
    await expect(finder(page)).toContainText('CPU fallback:');
    await expect(finder(page).getByRole('button', { name: /Check .* for RF-DETR Nano/ })).toBeVisible();
});


test('the finder keeps an explicit NPU choice even when GPU benchmarks faster', async ({ page }) => {
    const state = await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    const device = finder(page).getByRole('combobox', { name: 'Finder device' });
    await device.selectOption('intel_npu');
    await expect(unsaved(page)).toBeVisible();
    expect(state.saves).toEqual([]);
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0]).toMatchObject({ bird_crop_accurate_detector: 'rfdetr_nano', bird_crop_inference_provider: 'intel_npu' });
    await expect(unsaved(page)).toHaveCount(0);
    await expect(device).toHaveValue('intel_npu');
    await expect(device.locator('option[value="cuda"]')).toHaveJSProperty('disabled', true);
    await page.reload();
    await page.getByRole('link', { name: 'Detection', exact: true }).click();
    await expect(finder(page).getByRole('combobox', { name: 'Finder device' })).toHaveValue('intel_npu');
});


test('changing finder explains a saved device that the new finder has not validated', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', savedFinderProvider: 'intel_npu' });
    await finder(page).getByRole('radio', { name: /Standard/ }).check();
    const device = finder(page).getByRole('combobox', { name: 'Finder device' });
    await expect(device).toHaveValue('intel_npu');
    await expect(device.locator('option[value="intel_npu"]')).toHaveJSProperty('disabled', true);
    await expect(finder(page).getByRole('status').filter({ hasText: 'is saved but is not available' })).toBeVisible();
});
