import { expect, test, type Page } from '@playwright/test';
import { replayFeeder } from './accessibility-mock';

/**
 * The language menu is a menu button whose items are menu radios (WAI-ARIA APG, menu button
 * pattern): opening it moves focus to the checked language, the arrows move through the list with
 * wrap, Home and End jump to its ends, Enter or Space chooses, Escape closes it with focus back on
 * the button, and Tab closes it.
 */
const READY = { timeout: 15_000 };

async function openApp(page: Page) {
    await replayFeeder(page, 'light');
    await page.setViewportSize({ width: 1440, height: 900 });
    await page.goto('/');
    const trigger = page.getByRole('button', { name: 'English', exact: true }).first();
    await expect(trigger).toBeVisible(READY);
    return trigger;
}

const focusedName = (page: Page) => page.evaluate(() => {
    const active = document.activeElement;
    return active ? `${active.getAttribute('role') ?? active.tagName}:${active.textContent?.trim() ?? ''}` : 'none';
});

test('Enter opens the menu on the checked language', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('menu')).toBeVisible();
    await expect(page.getByRole('menuitemradio', { name: 'English' })).toBeFocused();
    await expect(trigger).toHaveAttribute('aria-expanded', 'true');
});

test('Arrow Down on the button opens the menu on the checked language', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('menuitemradio', { name: 'English' })).toBeFocused();
});

test('the arrows move through the languages with wrap, and Home and End reach the ends', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('Enter');
    const items = page.getByRole('menuitemradio');
    await expect(items.first()).toBeFocused();

    await page.keyboard.press('ArrowDown');
    await expect(items.nth(1)).toBeFocused();
    await page.keyboard.press('End');
    await expect(items.last()).toBeFocused();
    await page.keyboard.press('ArrowDown');
    await expect(items.first()).toBeFocused();
    await page.keyboard.press('ArrowUp');
    await expect(items.last()).toBeFocused();
    await page.keyboard.press('Home');
    await expect(items.first()).toBeFocused();
    // Only the focused item is a tab stop inside the menu.
    await expect(items.nth(1)).toHaveAttribute('tabindex', '-1');
});

test('Escape closes the menu and puts focus back on the button', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu')).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(trigger).toHaveAttribute('aria-expanded', 'false');
});

test('Tab closes the menu', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('Tab');
    await expect(page.getByRole('menu')).toHaveCount(0);
    expect(await focusedName(page)).not.toBe('BODY:');
});

test('Enter chooses a language, closes the menu and returns to the button', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('Enter');
    // English, Español, Français, Deutsch.
    for (let step = 0; step < 3; step += 1) await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('menuitemradio', { name: 'Deutsch' })).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(page.getByRole('menu')).toHaveCount(0);
    const german = page.getByRole('button', { name: 'Deutsch', exact: true }).first();
    await expect(german).toBeFocused(READY);
    await expect(page.locator('html')).toHaveAttribute('lang', 'de');
});

test('Space chooses a language too, and the menu opens on it next time', async ({ page }) => {
    const trigger = await openApp(page);
    await trigger.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    await expect(page.getByRole('menuitemradio', { name: 'Español' })).toBeFocused();
    await page.keyboard.press(' ');
    const spanish = page.getByRole('button', { name: 'Español', exact: true }).first();
    await expect(spanish).toBeFocused(READY);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('menuitemradio', { name: 'Español' })).toBeFocused();
    await expect(page.getByRole('menuitemradio', { name: 'Español' })).toHaveAttribute('aria-checked', 'true');
});
