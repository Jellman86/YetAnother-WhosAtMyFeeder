import { expect, test } from '@playwright/test';

test('a dialog whose code arrives late says it is opening, then opens', async ({ page }) => {
    await page.goto('/browser-tests/lazy-modal.html?delay=800');
    await page.getByRole('button', { name: 'Open record' }).click();
    await expect(page.getByRole('status')).toHaveText('Opening…');
    await expect(page.getByRole('dialog', { name: 'Record' })).toBeVisible();
    await expect(page.getByRole('status')).toHaveCount(0);
});

test('a dialog whose code fails to arrive says so in words, retries, and leaves the way it came', async ({ page }) => {
    await page.goto('/browser-tests/lazy-modal.html?fail=1');
    const opener = page.getByRole('button', { name: 'Open record' });
    await opener.click();
    const failure = page.getByRole('alertdialog', { name: 'This could not be opened' });
    await expect(failure).toBeVisible();
    await expect(failure).toContainText('Check your connection, then try again.');
    await expect(failure.getByRole('button', { name: 'Close' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(failure).toHaveCount(0);
    await expect(opener).toBeFocused();

    // Opening again tries the import again rather than repeating the cached failure.
    await opener.click();
    await expect(page.getByRole('dialog', { name: 'Record' })).toBeVisible();
    await expect(page.locator('[data-imports]')).toHaveText('2');
});

test('the retry button loads the dialog in place', async ({ page }) => {
    await page.goto('/browser-tests/lazy-modal.html?fail=1');
    await page.getByRole('button', { name: 'Open record' }).click();
    await page.getByRole('button', { name: 'Try opening again' }).click();
    await expect(page.getByRole('dialog', { name: 'Record' })).toBeVisible();
    await expect(page.getByRole('alertdialog')).toHaveCount(0);
});
