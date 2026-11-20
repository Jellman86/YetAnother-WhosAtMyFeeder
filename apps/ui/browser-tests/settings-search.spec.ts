import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { messageWords } from '../src/lib/settings/settings-search';
import { SETTINGS_SEARCH_INDEX, settingsSearchEntry } from '../src/lib/settings/settings-search-index';
import { openSettings, saveBar } from './settings-page-mock';

// The Settings search: a box first in the navigation that finds any setting by its name, its help
// or a synonym, opens the section and whatever is closed around it, and puts focus on its control.

/** Every switch that shows more settings is on, so each indexed setting is on the page to land on. */
const EVERYTHING_ON = {
    beta_garden_animals: true, garden_cameras: ['garden'], cameras: ['feeder'], mqtt_auth: true, birdnet_enabled: true,
    auth_enabled: true, auth_username: 'owner', auth_has_password: true, public_access_enabled: true, llm_enabled: true, llm_provider: 'gemini',
    ebird_enabled: true, inaturalist_enabled: true, birdweather_enabled: true, ha_weather_enabled: true, location_automatic: false,
    location_latitude: 51.5, location_longitude: -0.1, clips_enabled: true, recording_clip_enabled: true, auto_video_classification: true,
    media_cache_enabled: true, media_cache_clips: true, media_cache_high_quality_event_snapshots: true, media_cache_max_size_mb: 2048,
    range_filter_enabled: true, garden_notifications_enabled: true, notifications_discord_enabled: true, notifications_pushover_enabled: true,
    notifications_telegram_enabled: true, notifications_email_enabled: true, telemetry_enabled: true, debug_ui_enabled: true
};

/** Settings the fixture cannot show even with every switch on: they need a live answer from a service. */
const NEEDS_A_LIVE_SERVICE = new Set(['setting-recording-clips', 'setting-recording-before', 'setting-recording-after', 'setting-range-filter-level']);

const search = (page: Page) => page.getByRole('combobox', { name: 'Search settings' });
const results = (page: Page) => page.getByRole('listbox', { name: 'Search settings' }).getByRole('option');
const found = (page: Page) => page.locator('[data-settings-found]');

/** Whether focus is on the control of the setting an anchor names: inside its row, group or labelled control. */
async function focusIsOn(page: Page, anchor: string): Promise<boolean> {
    return page.evaluate((id) => {
        const element = document.getElementById(id);
        const active = document.activeElement;
        if (!element || !active || active === document.body) return false;
        const home = element.closest('[data-settings-row]') ?? element;
        if (home.contains(active)) return true;
        const labelled = document.querySelector(`[aria-labelledby~="${CSS.escape(id)}"]`);
        return Boolean(labelled && (labelled === active || labelled.contains(active)));
    }, anchor);
}

test.describe('on a wide screen', () => {
    test.use({ viewport: { width: 1440, height: 900 } });

    test('searching "gap" opens the visit gap in Identifying birds, with focus in its field', async ({ page }) => {
        await openSettings(page);
        await search(page).fill('gap');
        await expect(results(page).first()).toContainText('Visit gap');
        await expect(results(page).first()).toContainText('Identifying birds');
        await page.keyboard.press('Enter');
        await expect(page.locator('#visit-gap-seconds')).toBeFocused();
        await expect(page.locator('[data-settings-navigation]').getByRole('link', { name: 'Identifying birds', exact: true })).toHaveAttribute('aria-current', 'page');
        await expect(page.getByRole('heading', { level: 2, name: 'Identifying birds', exact: true })).toBeVisible();
        // The row is marked for a moment, and the search is calm again.
        await expect(found(page)).toContainText('Visit gap');
        await expect(search(page)).toHaveValue('');
        await expect(found(page)).toHaveCount(0, { timeout: 5_000 });
    });

    test('a synonym finds the cooldown under Alerts\' More options, which opens for it', async ({ page }) => {
        await openSettings(page);
        await search(page).fill('quiet');
        const option = results(page).filter({ hasText: 'Notification cooldown' });
        await expect(option).toContainText('Alerts › More options');
        await option.click();
        await expect(page.getByRole('switch', { name: 'Notification cooldown' })).toBeFocused();
        await expect(page.locator('[data-settings-more] button[aria-expanded]').first()).toHaveAttribute('aria-expanded', 'true');
    });

    test('an advanced setting is revealed: More options and its own disclosure both open', async ({ page }) => {
        await openSettings(page);
        await search(page).fill('worker processes');
        await expect(results(page).first()).toContainText('Identifying birds › More options › Advanced');
        await page.keyboard.press('Enter');
        await expect(page.locator('#live-worker-count')).toBeFocused();
        await expect(page.getByRole('button', { name: /Hide advanced options/ }).first()).toBeVisible();
    });

    test('the keyboard runs it: "/" focuses the box, arrows move, Escape closes then clears', async ({ page }) => {
        await openSettings(page);
        await page.locator('#settings-content').focus();
        await page.keyboard.press('/');
        await expect(search(page)).toBeFocused();
        await page.keyboard.type('camera');
        await expect(search(page)).toHaveAttribute('aria-expanded', 'true');
        const count = await results(page).count();
        expect(count).toBeGreaterThan(1);
        await expect(page.locator('[data-settings-search-status]')).toHaveText(`${count} settings found`);
        await expect(results(page).nth(0)).toHaveAttribute('aria-selected', 'true');
        await page.keyboard.press('ArrowDown');
        await expect(results(page).nth(1)).toHaveAttribute('aria-selected', 'true');
        await expect(search(page)).toHaveAttribute('aria-activedescendant', (await results(page).nth(1).getAttribute('id')) ?? '');
        await page.keyboard.press('ArrowUp');
        await page.keyboard.press('ArrowUp');
        await expect(results(page).nth(count - 1)).toHaveAttribute('aria-selected', 'true');
        await page.keyboard.press('Escape');
        await expect(search(page)).toHaveAttribute('aria-expanded', 'false');
        await expect(search(page)).toHaveValue('camera');
        await page.keyboard.press('Escape');
        await expect(search(page)).toHaveValue('');
        // A "/" typed into a field is a character, not the shortcut.
        await page.locator('#mqtt-server').fill('');
        await page.locator('#mqtt-server').pressSequentially('a/b');
        await expect(page.locator('#mqtt-server')).toHaveValue('a/b');
    });

    test('nothing found says so, with what can be searched', async ({ page }) => {
        await openSettings(page);
        await search(page).fill('zzzz');
        const empty = page.locator('[data-settings-search-empty]');
        await expect(empty).toContainText('No setting matches “zzzz”.');
        await expect(empty).toContainText('Search by a setting’s name');
        await expect(search(page)).toHaveAttribute('aria-expanded', 'false');
        await expect(page.locator('[data-settings-search-status]')).toHaveText('No setting matches “zzzz”.');
    });

    test('an unsaved draft survives a jump to another section and back', async ({ page }) => {
        const harness = await openSettings(page);
        await page.locator('#mqtt-server').fill('broker.lan');
        await expect(saveBar(page)).toBeVisible();
        await search(page).fill('history duration');
        await page.keyboard.press('Enter');
        await expect(page.locator('#retention-days')).toBeFocused();
        await expect(saveBar(page)).toContainText('1 unsaved change');
        await search(page).fill('mqtt');
        await results(page).filter({ hasText: 'Address and port' }).click();
        await expect(page.locator('#mqtt-server')).toBeFocused();
        await expect(page.locator('#mqtt-server')).toHaveValue('broker.lan');
        expect(harness.writes).toEqual([]);
    });

    test('a setting behind a switch that is off lands on the switch and says why', async ({ page }) => {
        await openSettings(page, { llm_enabled: false });
        await search(page).fill('prompt style');
        await page.keyboard.press('Enter');
        await expect(page.getByRole('switch', { name: /AI/ }).first()).toBeFocused({ timeout: 15_000 });
        await expect(page.locator('[data-settings-search-note]')).toContainText('is shown once');
    });

    test('the search follows the language, and still knows English synonyms', async ({ page }) => {
        await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
        await openSettings(page);
        const box = page.locator('[data-settings-search-input]');
        await box.fill('BESUCHSAB');
        const option = page.locator('[data-settings-search-option="setting-visit-gap"]');
        await expect(option).toBeVisible();
        await box.fill('dedupe');
        await expect(option).toBeVisible();
    });

    test('every indexed setting lands on its own control', async ({ page }) => {
        test.setTimeout(600_000);
        await openSettings(page, EVERYTHING_ON);
        const box = page.locator('[data-settings-search-input]');
        // The page's own English dictionary, so the test types what the reader would see.
        const dictionary = await page.evaluate(async () => (await import(/* @vite-ignore */ `${location.origin}/src/lib/i18n/locales/en.ts`)).default as unknown);
        const labelOf = (key: string): string => {
            let node: unknown = dictionary;
            for (const part of key.split('.')) node = node && typeof node === 'object' ? (node as Record<string, unknown>)[part] : undefined;
            return typeof node === 'string' ? messageWords(node) : '';
        };
        const missed: string[] = [];
        for (const entry of SETTINGS_SEARCH_INDEX) {
            if (NEEDS_A_LIVE_SERVICE.has(entry.anchor)) continue;
            // Chosen through the box, as a reader would, by its own label.
            const label = labelOf(entry.labelKey);
            await box.fill(label);
            const option = page.locator(`[data-settings-search-option="${entry.anchor}"]`);
            if ((await option.count()) === 0) {
                missed.push(`${entry.anchor}: not offered for its own label "${label}"`);
                continue;
            }
            await option.click();
            const landed = await expect.poll(() => focusIsOn(page, entry.anchor), { timeout: 10_000 }).toBe(true).then(() => true, () => false);
            if (!landed) {
                const where = await page.evaluate(() => document.activeElement?.id || document.activeElement?.tagName || '');
                missed.push(`${entry.anchor}: focus went to ${where}`);
            }
        }
        expect(missed).toEqual([]);
        // An entry said to need a live service must still be a real entry.
        for (const anchor of NEEDS_A_LIVE_SERVICE) expect(settingsSearchEntry(anchor), anchor).not.toBeNull();
    });
});

test.describe('on a phone', () => {
    test.use({ viewport: { width: 390, height: 844 } });

    test('the search sits above the section list, fits the screen and lands on the setting', async ({ page }) => {
        await openSettings(page);
        const box = await search(page).boundingBox();
        const select = await page.locator('#settings-tab-select').boundingBox();
        expect(box && select).toBeTruthy();
        expect((box?.y ?? 0) + (box?.height ?? 0)).toBeLessThanOrEqual(select?.y ?? 0);
        expect(box?.height ?? 0).toBeGreaterThanOrEqual(44);
        await search(page).fill('gap');
        const panel = await page.locator('[data-settings-search-panel]').boundingBox();
        expect((panel?.x ?? -1)).toBeGreaterThanOrEqual(0);
        expect((panel?.x ?? 0) + (panel?.width ?? 0)).toBeLessThanOrEqual(390);
        await results(page).first().click();
        await expect(page.locator('#visit-gap-seconds')).toBeFocused();
        await expect(page.locator('#settings-tab-select')).toHaveValue('identification');
        // The field is in view, clear of the section name that stays at the top.
        // Once the scroll has come to rest.
        await expect.poll(async () => {
            const field = await page.locator('#visit-gap-seconds').boundingBox();
            const heading = await page.locator('[data-settings-section-heading]').boundingBox();
            if (!field || !heading) return false;
            return field.y > heading.y + heading.height && field.y + field.height <= 844;
        }).toBe(true);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    });
});

for (const theme of ['light', 'dark'] as const) {
    test.describe(`${theme} theme`, () => {
        test.use({ viewport: { width: 1440, height: 900 }, colorScheme: theme });

        test('the open search, its empty state and a result just opened have no serious accessibility violation', async ({ page }) => {
            await page.addInitScript((chosen) => localStorage.setItem('theme', chosen), theme);
            await openSettings(page);
            const serious = async (): Promise<string[]> =>
                (await new AxeBuilder({ page }).analyze()).violations
                    .filter((violation) => violation.impact === 'serious' || violation.impact === 'critical')
                    .flatMap((violation) => violation.nodes.map((node) => `${violation.id}: ${node.target.join(' ')}`));
            await search(page).fill('camera');
            await expect(results(page).first()).toBeVisible();
            expect(await serious()).toEqual([]);
            await search(page).fill('zzzz');
            await expect(page.locator('[data-settings-search-empty]')).toBeVisible();
            expect(await serious()).toEqual([]);
            await search(page).fill('gap');
            await page.keyboard.press('Enter');
            await expect(found(page)).toHaveCount(1);
            expect(await serious()).toEqual([]);
        });
    });
}

test('with reduced motion the opened setting is outlined, with no animation', async ({ page }) => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await openSettings(page);
    await search(page).fill('gap');
    await page.keyboard.press('Enter');
    await expect(found(page)).toHaveCount(1);
    const style = await found(page).evaluate((element) => ({ animation: getComputedStyle(element).animationName, outline: getComputedStyle(element).outlineStyle }));
    expect(style).toEqual({ animation: 'none', outline: 'solid' });
});
