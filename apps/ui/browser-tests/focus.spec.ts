import { test, expect } from '@playwright/test';

test.beforeEach(async ({ page }) => {
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/focus.html');
});

test('Escape returns to the record opener and Tab continues in the page', async ({ page, browserName }) => {
    const opener = page.getByRole('button', { name: 'Open record', exact: true });
    await opener.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Close record', exact: true })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(opener).toBeFocused();
    // Safari's default keyboard preference uses Option-Tab for all controls.
    // https://support.apple.com/en-ie/guide/safari/cpsh003/mac
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    await expect(page.getByRole('button', { name: 'Navigate elsewhere', exact: true })).toBeFocused();
});

test('a nested dialog returns focus to its own opener before the record closes', async ({ page }) => {
    await page.getByRole('button', { name: 'Open record', exact: true }).focus();
    await page.keyboard.press('Enter');
    const nested = page.getByRole('button', { name: 'Open confirmation', exact: true });
    await nested.focus(); await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Cancel confirmation', exact: true })).toBeFocused();
    await page.keyboard.press('Escape'); await expect(nested).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('button', { name: 'Open record', exact: true })).toBeFocused();
});

test('a removed opener falls back to the page content', async ({ page, browserName }) => {
    await page.getByRole('button', { name: 'Open record', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: 'Remove opener and close', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('main')).toBeFocused();
    // Safari's default keyboard preference uses Option-Tab for all controls.
    // https://support.apple.com/en-ie/guide/safari/cpsh003/mac
    await page.keyboard.press(browserName === 'webkit' ? 'Alt+Tab' : 'Tab');
    await expect(page.getByRole('button', { name: 'Navigate elsewhere', exact: true })).toBeFocused();
});

test('closing the parent first does not steal focus from its still-open child', async ({ page }) => {
    await page.getByRole('button', { name: 'Open record', exact: true }).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('button', { name: 'Open confirmation', exact: true }).focus();
    await page.keyboard.press('Enter');
    const closeParent = page.getByRole('button', { name: 'Close parent first', exact: true });
    await closeParent.focus(); await page.keyboard.press('Enter'); await expect(closeParent).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('main')).toBeFocused();
});

test('closing immediately cancels delayed focus instead of focusing the detached dialog', async ({ page }) => {
    await page.getByRole('button', { name: 'Open record', exact: true }).focus();
    await page.keyboard.press('Enter');
    // Close through the mounted control before the delayed initial focus runs.
    await page.getByRole('button', { name: 'Close record', exact: true }).evaluate(node => {
        if (!(node instanceof HTMLButtonElement)) throw new Error('Expected the dialog close button');
        node.click();
    });
    await page.waitForTimeout(75);
    await expect(page.getByRole('button', { name: 'Open record', exact: true })).toBeFocused();
    await expect(page.getByRole('dialog')).toHaveCount(0);
});

test('closing a dialog preserves focus already moved elsewhere', async ({ page }) => {
    await page.getByRole('button', { name: 'Open record', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Close record', exact: true })).toBeFocused();
    await page.getByRole('button', { name: 'Navigate elsewhere', exact: true }).focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('button', { name: 'Navigate elsewhere', exact: true })).toBeFocused();
});
