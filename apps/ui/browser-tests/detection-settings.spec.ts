import { test, expect, type Page } from '@playwright/test';
import { openDetectionSettings } from './detection-settings-mock';

const unsaved = (page: Page) => page.getByRole('region', { name: 'Unsaved changes' });
const finder = (page: Page) => page.getByRole('group', { name: 'Bird finder' });

test('the bird finder choice waits for Save changes and saves with the rest of the form', async ({ page }) => {
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
    await expect(finder(page)).toContainText('Save changes to switch');
    expect(state.saves).toEqual([]);

    await page.locator('#bird-model-region-override').selectOption('eu');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].bird_crop_accurate_detector).toBe('rfdetr_nano');
    expect(state.saves[0].bird_model_region_override).toBe('eu');
    await expect(unsaved(page)).toHaveCount(0);
    await expect(wide).toBeChecked();
    await expect(finder(page)).not.toContainText('Save changes to switch');
    expect(errors).toEqual([]);
});

test('an unchanged form still sends the saved finder, so an unrelated save never resets it', async ({ page }) => {
    const state = await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    await expect(finder(page).getByRole('radio', { name: /Wide frame/ })).toBeChecked();
    await page.locator('#bird-model-region-override').selectOption('na');
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].bird_crop_accurate_detector).toBe('rfdetr_nano');
});

test('a failed save keeps the staged finder and says the settings were not saved', async ({ page }) => {
    const state = await openDetectionSettings(page, { saveFails: true });
    const wide = finder(page).getByRole('radio', { name: /Wide frame/ });
    await wide.check();
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect(unsaved(page).locator('[data-save-problem]')).toContainText('Nothing was saved');
    await expect(wide).toBeChecked();
    await expect(unsaved(page)).toBeVisible();
    expect(state.saves).toEqual([]);
});

test('a chosen finder that is not downloaded is explained and offers the download', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', rfdetrInstalled: false });
    await expect(finder(page)).toContainText('not downloaded yet');
    await expect(finder(page).getByRole('button', { name: 'Download RF-DETR Nano' })).toBeVisible();
});

const RFDETR = 'bird_crop_detector_accurate_rfdetr_nano';
const runsOn = (page: Page) => finder(page).locator('[data-finder-runs-on]');
const device = (page: Page) => finder(page).getByRole('combobox', { name: 'Device', exact: true });
const npuFailed = {
    state: 'failed', model_id: RFDETR, providers: ['intel_npu'], checked_at: '2026-11-12T08:30:00Z',
    reason: 'The accelerators did not match the CPU on saved bird photos, so the finder stays on the CPU.'
};

test('the finder options state cost only, and where the finder runs is said once', async ({ page }) => {
    await openDetectionSettings(page);
    const options = finder(page).locator('label').filter({ has: page.getByRole('radio') });
    await expect(options).toHaveCount(2);
    for (const option of await options.all()) {
        await expect(option).not.toContainText(/CPU until|Recommended|device check|accelerator/);
    }
    // One rounded size per model, the same figure the catalogue uses everywhere.
    await expect(options.first()).toContainText('19 MB download · ~512 MB RAM');
    await expect(options.nth(1)).toContainText('103 MB download');
    await expect(runsOn(page)).toHaveCount(1);
    // YOLOX-Tiny has no passing check here, so nothing is claimed for an accelerator.
    await expect(runsOn(page)).toHaveText('CPU · no accelerator has passed a check on this host yet');
    await expect(runsOn(page)).toHaveAttribute('data-finder-runs-on', 'never_checked');
    // Only labels are heavy. Values, option meta and help are normal weight.
    const heavy = await finder(page).evaluate(node => [...node.querySelectorAll<HTMLElement>('[data-finder-device-panel] p, [data-finder-device-panel] select, [data-finder-option-meta]')]
        .filter(element => Number(getComputedStyle(element).fontWeight) >= 600)
        .map(element => (element.textContent ?? '').trim().slice(0, 40)));
    expect(heavy).toEqual([]);
});

test('a finder running on its saved device says which, and dates the check only when one measured it', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    await expect(runsOn(page)).toHaveText('Intel NPU · passed its device check on this host');
});

test('a passed check that measured the saved device is dated', async ({ page }) => {
    await openDetectionSettings(page, {
        savedFinder: 'rfdetr_nano', savedFinderProvider: 'intel_npu',
        finderDeviceCheck: { state: 'succeeded', model_id: RFDETR, providers: ['intel_npu'], reason: null, checked_at: '2026-11-08T07:15:00Z' }
    });
    await expect(runsOn(page)).toHaveText(/^\s*Intel NPU · passed its device check on 0?8[ /.]/);
    await expect(finder(page).locator('[data-finder-device-note]')).toHaveCount(0);
});

test('a finder that fell back after a failed check says so with the date and the measured cause, and keeps the saved device', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', savedFinderProvider: 'intel_npu', rfdetrEvidence: ['cpu'], finderDeviceCheck: npuFailed });
    await expect(runsOn(page)).toHaveText(/^\s*CPU · Intel NPU failed the device check on 12[ /.].*\(the boxes did not match the CPU's\)\s*$/);
    await expect(runsOn(page)).toHaveAttribute('data-finder-runs-on', 'failed');
    // The saved device is still chosen and still selectable, named for what is known about it.
    await expect(device(page)).toHaveValue('intel_npu');
    const npu = device(page).locator('option[value="intel_npu"]');
    await expect(npu).toHaveText('Intel NPU · not passed on this host');
    await expect(npu).toHaveJSProperty('disabled', false);
    await expect(device(page).locator('option').first()).toHaveText('Automatic (NPU, then GPU, then CPU)');
    await expect(finder(page).locator('[data-finder-device-note]'))
        .toHaveText('Saved: Intel NPU. See Runs on above for the device currently used, or Check devices.');
    await expect(finder(page)).not.toContainText('in this image');
    await expect(finder(page)).not.toContainText('No check has finished');
    // The server refuses a newly chosen device that has not passed, so that one is named but not offered.
    const gpu = device(page).locator('option[value="intel_gpu"]');
    await expect(gpu).toHaveText('Intel GPU · not passed on this host');
    await expect(gpu).toHaveJSProperty('disabled', true);
    // Moving away and back to the saved device is still possible.
    await device(page).selectOption('auto');
    await expect(finder(page).locator('[data-finder-device-note]')).toHaveCount(0);
    await device(page).selectOption('intel_npu');
    await expect(finder(page).locator('[data-finder-device-note]')).toContainText('Saved: Intel NPU.');
});

test('a saved NPU preference names the GPU when only the GPU has current passing evidence', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', savedFinderProvider: 'intel_npu', rfdetrEvidence: ['intel_gpu', 'cpu'], finderDeviceCheck: npuFailed });
    await expect(runsOn(page)).toHaveText('Intel GPU · passed its device check on this host');
    await expect(device(page)).toHaveValue('intel_npu');
});

test('a cause the backend does not name is left unsaid', async ({ page }) => {
    await openDetectionSettings(page, {
        savedFinder: 'rfdetr_nano', rfdetrEvidence: ['cpu'], finderDeviceCheck: { ...npuFailed, reason: 'A reason this page has never seen.' }
    });
    await expect(runsOn(page)).toHaveText(/^\s*CPU · Intel NPU failed the device check on 12[ /.][^(]*$/);
});

test('a running check is named on the row and on the button', async ({ page }) => {
    await openDetectionSettings(page, {
        savedFinder: 'rfdetr_nano', rfdetrEvidence: ['cpu'],
        finderDeviceCheck: { state: 'running', model_id: RFDETR, providers: ['intel_gpu', 'intel_npu'], reason: null, checked_at: '2026-11-15T19:00:00Z' }
    });
    await expect(runsOn(page)).toHaveText('Checking Intel GPU and Intel NPU…');
    await expect(finder(page).getByRole('button', { name: 'Checking…', exact: true })).toBeDisabled();
});

test('Check devices is one short button with its hint under it, scoped to the chosen finder alone', async ({ page }) => {
    const runs: unknown[] = [];
    await openDetectionSettings(page);
    await page.route('**/api/diagnostics/model-eval/runs', route => {
        if (route.request().method() !== 'POST') return route.fallback();
        runs.push(route.request().postDataJSON());
        return route.fulfill({ json: { run_id: 'finder-check' } });
    });
    const check = finder(page).getByRole('button', { name: 'Check devices for the bird finder', exact: true });
    await expect(check).toBeVisible();
    await expect(check).toHaveAccessibleDescription(/uses the fastest that matches\. The identification model is not changed\./);
    const order = await finder(page).evaluate(node => {
        const top = (selector: string) => (node.querySelector(selector) as HTMLElement).getBoundingClientRect().top;
        return top('#bird-finder-check-hint') > top('[data-finder-actions] button') && top('[data-finder-repair]') > top('#bird-finder-check-hint');
    });
    expect(order).toBe(true);
    await check.click();
    await expect.poll(() => runs.length).toBe(1);
    // Scoped to the finder: no identification model is activated or downloaded for it.
    expect(runs[0]).toMatchObject({ sweep_devices: true, compat_only: true, sweep_all_models: false, model_ids: ['bird_crop_detector_accurate_yolox_tiny'] });
});

test('re-download waits behind Repair, and the background behind "How the finder works"', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    const redownload = finder(page).getByRole('button', { name: 'Re-download RF-DETR Nano' });
    await expect(redownload).toBeHidden();
    await finder(page).locator('[data-finder-repair] summary').focus();
    await page.keyboard.press('Enter');
    await expect(redownload).toBeVisible();
    const how = finder(page).locator('[data-finder-how]');
    await expect(how.getByText('takes effect when you save')).toBeHidden();
    await how.locator('summary').click();
    await expect(how).toContainText("Frigate's tracking box");
    await expect(how).toContainText('takes effect when you save. If the device becomes unavailable, a verified recovery device or CPU is used.');
});

test('the last completed run is shown under the fact it qualifies', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', finderExecution: {
        model_id: RFDETR, provider: 'cpu', requested_provider: 'intel_gpu',
        devices: ['CPUExecutionProvider'], checked_at: '2026-10-25T08:00:00Z', fallback_reason: 'runtime_failed'
    } });
    await expect(runsOn(page)).toContainText('CPU · last confirmed use on');
    await expect(runsOn(page)).toContainText('Last completed run: CPU');
    await expect(runsOn(page)).toContainText('CPU fallback:');
});

test('with no completed run nothing is said about one', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    await expect(runsOn(page)).toBeVisible();
    await expect(finder(page)).not.toContainText('Last completed run');
    await expect(finder(page)).not.toContainText('No check has finished');
});

test('the finder keeps an explicit NPU choice even when GPU benchmarks faster', async ({ page }) => {
    const state = await openDetectionSettings(page, { savedFinder: 'rfdetr_nano' });
    await device(page).selectOption('intel_npu');
    await expect(unsaved(page)).toBeVisible();
    expect(state.saves).toEqual([]);
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0]).toMatchObject({ bird_crop_accurate_detector: 'rfdetr_nano', bird_crop_inference_provider: 'intel_npu' });
    await expect(unsaved(page)).toHaveCount(0);
    await expect(device(page)).toHaveValue('intel_npu');
    // A device this host does not offer the finder is not listed at all.
    await expect(device(page).locator('option[value="cuda"]')).toHaveCount(0);
    await page.reload();
    await page.getByRole('link', { name: 'Models', exact: true }).click();
    await expect(device(page)).toHaveValue('intel_npu');
    await expect(runsOn(page)).toHaveText('Intel NPU · passed its device check on this host');
});

test('changing finder says a saved device the new finder has not passed on cannot be saved with it', async ({ page }) => {
    await openDetectionSettings(page, { savedFinder: 'rfdetr_nano', savedFinderProvider: 'intel_npu' });
    await finder(page).getByRole('radio', { name: /Standard/ }).check();
    await expect(device(page)).toHaveValue('intel_npu');
    await expect(device(page).locator('option[value="intel_npu"]')).toHaveText('Intel NPU · not passed on this host');
    await expect(finder(page).locator('[data-finder-device-note]'))
        .toHaveText('Intel NPU has not passed a check for this finder on this host, so it cannot be saved yet. Check devices, or choose Automatic.');
});

test('a saved provider this host cannot use is flagged in words beside the choice', async ({ page }) => {
    await openDetectionSettings(page, { savedProvider: 'cuda' });
    const provider = page.locator('#inference-provider');
    await expect(provider).toHaveValue('cuda');
    await expect(page.getByRole('status').filter({ hasText: 'Saved: NVIDIA CUDA. It is not among the devices this model can use here now' })).toBeVisible();
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
    await page.getByRole('button', { name: 'Save changes', exact: true }).click();
    await expect.poll(() => state.saves.length).toBe(1);
    expect(state.saves[0].live_worker_count).toBe(2);
    expect(state.saves[0].image_execution_mode).toBe('subprocess');
});

for (const width of [320, 393]) {
    test(`the Models tab reflows at ${width}px with 200% text`, async ({ page }) => {
        await page.setViewportSize({ width, height: 900 });
        await openDetectionSettings(page);
        await page.addStyleTag({ content: 'html{font-size:200%!important}' });
        await expect(page.locator('#bird-model-region-override')).toBeVisible();
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
