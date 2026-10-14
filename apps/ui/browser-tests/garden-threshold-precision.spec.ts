import { expect, test } from '@playwright/test';
for (const calibrated of [0.63, 0.625]) {
test(`calibrated ${calibrated} threshold is valid and saves only the Garden setting`, async ({ page }) => {
    let current = calibrated;
    let saved: unknown;
    await page.route('**/api/settings', route => {
        saved = route.request().postDataJSON();
        current = 0.64;
        return route.fulfill({ json: { status: 'success' } });
    });
    await page.route('**/api/garden?**', route => route.fulfill({ json: { items: [], total: 0, limit: 8, offset: 0 } }));
    await page.route('**/api/garden/identification', route => route.fulfill({ json: { country: 'GBR', catalogue_ready: true, busy: false, error: null, models: [] } }));
    await page.route('**/api/garden/motion', route => route.fulfill({ json: { cameras: ['patio'], installed: true, catalogue_ready: true, busy: false, state: 'waiting', message: 'Recording scanned.', interval_seconds: 10, catchup_seconds: 1800, queue_limit: 24, photo_limit: 128, photo_retention_days: 3, animal_confidence: current } }));
    await page.goto('/browser-tests/garden.html');
    await page.locator('[data-garden-motion] > summary').click();
    const threshold = page.getByRole('spinbutton', { name: 'Animal proposal threshold' });
    await expect(threshold).toHaveValue(String(calibrated));
    expect(await threshold.evaluate((input: HTMLInputElement) => ({ valid: input.checkValidity(), stepMismatch: input.validity.stepMismatch }))).toEqual({ valid: true, stepMismatch: false });
    await threshold.press('ArrowUp');
    await expect(threshold).toHaveValue(calibrated === 0.63 ? '0.64' : '0.626');
    await threshold.press('ArrowDown');
    await expect(threshold).toHaveValue(String(calibrated));
    if (calibrated === 0.625) {
        for (let count = 0; count < 5; count++) await threshold.press('ArrowUp');
        await expect(threshold).toHaveValue('0.63');
        await threshold.press('ArrowUp');
        await expect(threshold).toHaveValue('0.631');
    }
    const save = page.getByRole('button', { name: 'Save animal threshold' });
    if (calibrated === 0.63) await expect(save).toBeDisabled();
    await threshold.fill('0.64');
    await save.click();
    await expect(threshold).toHaveValue('0.64');
    await expect(save).toBeDisabled();
    expect(saved).toEqual({ garden_motion_confidence: 0.64 });
    for (const outside of ['0.49', '0.96']) {
        await threshold.fill(outside);
        await expect(save).toBeDisabled();
        expect(await threshold.evaluate((input: HTMLInputElement) => input.checkValidity())).toBe(false);
    }
});
}
