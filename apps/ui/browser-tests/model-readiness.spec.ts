import { expect, test } from '@playwright/test';
import { openDetectionSettings } from './detection-settings-mock';

// Settings › Models states the chosen model by the shared readiness rule. "In use" is said only of
// a model that is selected and running; a selected model in any other state says that state, and
// one that needs a person has one primary action that recovers it.
test.use({ viewport: { width: 1280, height: 900 } });

const IN_APP = { image_execution_mode: 'in_process', runtime_source: 'in_process', active_model_installed: true };

test('a running model is in use', async ({ page }) => {
    await openDetectionSettings(page, { statusExtra: { active_model_installed: true } });
    const current = page.locator('[data-current-model]');
    await expect(current).toHaveAttribute('data-model-readiness', 'running');
    await expect(current).toContainText('In use now');
    await expect(current.locator('[data-model-recovery]')).toHaveCount(0);
});

test('a chosen model that could not load is not "In use now", and has a primary recovery', async ({ page }, testInfo) => {
    await openDetectionSettings(page, { statusExtra: { ...IN_APP, loaded: false, error: 'runtime could not open the model' } });
    const current = page.locator('[data-current-model]');
    await expect(current).toHaveAttribute('data-model-readiness', 'failed');
    await expect(current).toContainText('Chosen · Could not load');
    await expect(current).not.toContainText('In use');
    const recovery = current.locator('[data-model-recovery="revalidate"]');
    await expect(recovery).toHaveText('Check and load again');
    await expect(recovery).toHaveClass(/btn-primary/);
    // It is the one loud button on the page: no other model's action competes with it.
    await expect(page.locator('[data-identification-model] .btn-primary')).toHaveCount(1);
    await current.scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('models-chosen-could-not-load.png') });
});

test('a chosen model that is still loading says so and offers no recovery', async ({ page }) => {
    await openDetectionSettings(page, { statusExtra: { ...IN_APP, loaded: null } });
    const current = page.locator('[data-current-model]');
    await expect(current).toHaveAttribute('data-model-readiness', 'loading');
    await expect(current).toContainText('Chosen · Loading');
    await expect(current).not.toContainText('In use');
    await expect(current.locator('[data-model-recovery]')).toHaveCount(0);
});

test('a classifier that reports no evidence leaves the chosen model "Not reported"', async ({ page }) => {
    await openDetectionSettings(page, { statusExtra: { runtime_source: null, loaded: null, active_model_installed: true } });
    const current = page.locator('[data-current-model]');
    await expect(current).toHaveAttribute('data-model-readiness', 'unknown');
    await expect(current).toContainText('Chosen · Not reported');
    await expect(current).not.toContainText('In use');
});
