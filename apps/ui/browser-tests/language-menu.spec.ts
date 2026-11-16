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

const SPANISH_MODULE = (url: URL) => /\/i18n\/locales\/es\.ts$/.test(url.pathname);

test('a language that fails to load keeps focus in the menu, says so, and Escape still closes it', async ({ page }) => {
    const trigger = await openApp(page);
    await page.route(SPANISH_MODULE, (route) => route.fulfill({ status: 503, body: 'unavailable' }));
    await trigger.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    const spanish = page.getByRole('menuitemradio', { name: 'Español' });
    await expect(spanish).toBeFocused();
    await page.keyboard.press('Enter');

    await expect(page.getByRole('menu').getByRole('alert')).toContainText('could not be loaded', READY);
    await expect(spanish).toBeFocused();
    await expect(spanish).toHaveAttribute('aria-checked', 'false');
    await expect(page.getByRole('menuitemradio', { name: 'English' })).toHaveAttribute('aria-checked', 'true');
    // The arrows still work, and Escape still closes the menu with focus back on the button.
    await page.keyboard.press('ArrowUp');
    await expect(page.getByRole('menuitemradio', { name: 'English' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('menu')).toHaveCount(0);
    await expect(trigger).toBeFocused();
});

test('while a language loads, its item keeps focus and every item says it is unavailable', async ({ page }) => {
    const trigger = await openApp(page);
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route(SPANISH_MODULE, async (route) => { await held; await route.continue(); });
    await trigger.focus();
    await page.keyboard.press('Enter');
    await page.keyboard.press('ArrowDown');
    const spanish = page.getByRole('menuitemradio', { name: 'Español' });
    await page.keyboard.press('Enter');

    await expect(spanish).toHaveAttribute('aria-disabled', 'true');
    await expect(page.getByRole('menuitemradio', { name: 'Français' })).toHaveAttribute('aria-disabled', 'true');
    await expect(spanish).toBeFocused();
    // A second choice while the first is loading does nothing.
    await page.keyboard.press('ArrowDown');
    await page.keyboard.press('Enter');
    await expect(page.getByRole('menu')).toBeVisible();

    release();
    await expect(page.getByRole('menu')).toHaveCount(0, READY);
    await expect(page.getByRole('button', { name: 'Español', exact: true }).first()).toBeFocused();
    await expect(page.locator('html')).toHaveAttribute('lang', 'es');
});
