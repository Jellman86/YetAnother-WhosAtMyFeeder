import AxeBuilder from '@axe-core/playwright';
import { expect, test, type Page } from '@playwright/test';
import { messageWords } from '../src/lib/settings/settings-search';
import { SETTINGS_SEARCH_INDEX, settingsSearchInMore } from '../src/lib/settings/settings-search-index';
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

/** The two services whose answers decide whether a row is drawn, answered as a working install does. */
const SERVICES_ANSWER = (path: string): { json: unknown } | undefined => {
    if (path.endsWith('/frigate/recording-clip-capability')) {
        return { json: { supported: true, recordings_enabled: true, retention_days: 7, eligible_cameras: ['feeder'], ineligible_cameras: {} } };
    }
    if (path.endsWith('/range-filter/status')) {
        return { json: {
            reason: 'active', enabled: true, filtering: true, ebird_configured: true, species_in_range: 412, region_species_total: 415,
            region: { code: 'GB-ENG-KEN', codes: ['GB-ENG-KEN'], name: 'Kent, England, GB', level: 'county', note: null },
            refreshed_at: new Date(Date.now() - 2 * 86_400_000).toISOString(), model: { bird_species: 1486, out_of_range: 803, unmatched: 0 }
        } };
    }
    return undefined;
};

const search = (page: Page) => page.getByRole('combobox', { name: 'Search settings' });
const results = (page: Page) => page.getByRole('listbox', { name: 'Search settings' }).getByRole('option');
const found = (page: Page) => page.locator('[data-settings-found]');

/**
 * Whether focus is on the setting an anchor names: on a control inside its row or on the control its
 * label names. A group lands on its own heading, not on something inside the card.
 */
async function focusIsOn(page: Page, anchor: string, group: boolean): Promise<boolean> {
    return page.evaluate(([id, isGroup]) => {
        const element = document.getElementById(id as string);
        const active = document.activeElement;
        if (!element || !active || active === document.body) return false;
        if (isGroup) return /^H[2-6]$/.test(active.tagName) && (active === element || element.contains(active)) && !active.closest('[data-settings-section-body]');
        const home = element.closest('[data-settings-row]') ?? element;
        if (home.contains(active)) return true;
        const labelled = document.querySelector(`[aria-labelledby~="${CSS.escape(id)}"]`);
        return Boolean(labelled && (labelled === active || labelled.contains(active)));
    }, [anchor, group] as const);
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

    test('a synonym finds the cooldown under Notifications\' More options, which opens for it', async ({ page }) => {
        await openSettings(page);
        await search(page).fill('quiet');
        const option = results(page).filter({ hasText: 'Notification cooldown' });
        await expect(option).toContainText('Notifications › More options');
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
        // The count is said once: the input is not also described by it.
        await expect(search(page)).not.toHaveAttribute('aria-describedby');
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

    test('when more settings match than are listed, the count says how many there are', async ({ page }) => {
        await openSettings(page);
        await search(page).fill('notification');
        await expect(results(page)).toHaveCount(8);
        const status = page.locator('[data-settings-search-status]');
        await expect(status).toHaveText(/^\d+ settings match; showing 8\. Type more to narrow them\.$/);
        expect(Number((await status.innerText()).split(' ')[0])).toBeGreaterThan(8);
        await search(page).fill('notification cooldown');
        await expect(status).toHaveText('1 setting found');
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
        const aiSwitch = page.getByRole('switch', { name: /AI/ }).first();
        await expect(aiSwitch).toBeFocused({ timeout: 15_000 });
        // Said in a region that was on the page, empty, before there was anything to say.
        await expect(page.locator('[data-settings-search-note]')).toHaveText(/is shown once/);
        // And shown beside the switch, which is described by it.
        const beside = page.locator('[data-settings-found-note]');
        await expect(beside).toBeVisible();
        await expect(beside).toHaveText(await page.locator('[data-settings-search-note]').innerText());
        expect(await aiSwitch.getAttribute('aria-describedby')).toContain('settings-found-note');
        // The AI provider's switch is beside its heading, so the note is in that group's header.
        expect(await beside.evaluate((note) => Boolean(note.closest('#settings-group-ai-connection header')))).toBe(true);
        // Another section, and the note has gone from both places.
        await page.locator('[data-settings-navigation]').getByRole('link', { name: 'Notifications', exact: true }).click();
        await expect(page.locator('[data-settings-search-note]')).toHaveText('');
        await expect(beside).toHaveCount(0);
    });

    test('the note region is on the page, empty, before any search', async ({ page }) => {
        await openSettings(page);
        const note = page.locator('[data-settings-search-note]');
        await expect(note).toHaveCount(1);
        await expect(note).toHaveAttribute('role', 'status');
        await expect(note).toHaveText('');
    });

    test('a jump still waiting is called off when the reader opens another section: no pull back, no note', async ({ page }) => {
        // "Prompt style" is behind the AI switch, which is off: the jump waits for the row, then turns to the switch.
        await openSettings(page, { llm_enabled: false });
        const rail = page.locator('[data-settings-navigation]');
        await search(page).fill('prompt style');
        await page.keyboard.press('Enter');
        await rail.getByRole('link', { name: 'Notifications', exact: true }).click();
        await expect(rail.getByRole('link', { name: 'Notifications', exact: true })).toHaveAttribute('aria-current', 'page');
        // Long enough for the old jump to have gone to the switch and come back for the reader.
        await page.waitForTimeout(3500);
        await expect(rail.getByRole('link', { name: 'Notifications', exact: true })).toHaveAttribute('aria-current', 'page');
        await expect(page.locator('main')).toHaveAttribute('data-fixture-route', '/settings/notifications');
        await expect(found(page)).toHaveCount(0);
        await expect(page.locator('[data-settings-found-note]')).toHaveCount(0);
        await expect(page.locator('[data-settings-search-note]')).toHaveText('');
        expect(await page.evaluate(() => Boolean(document.activeElement?.closest('[data-settings-part="ai"]')))).toBe(false);
    });

    test('a jump still waiting is called off when the reader types in another field: focus stays with them', async ({ page }) => {
        const slow = { on: false };
        await openSettings(page, {}, {
            respond: async () => {
                // The section's reads take their time, so the jump waits for them before it scrolls.
                if (slow.on) await new Promise((resolve) => setTimeout(resolve, 2500));
                return undefined;
            }
        });
        slow.on = true;
        await search(page).fill('worker processes');
        await page.keyboard.press('Enter');
        const gap = page.locator('#visit-gap-seconds');
        await expect(gap).toBeVisible();
        await gap.click();
        await gap.press('ControlOrMeta+a');
        await gap.pressSequentially('45', { delay: 400 });
        await page.waitForTimeout(4500);
        await expect(gap).toBeFocused();
        await expect(gap).toHaveValue('45');
        await expect(found(page)).toHaveCount(0);
        await expect(page.locator('[data-settings-search-note]')).toHaveText('');
    });

    test('starting to type a new search calls off the jump still waiting, before anything else is chosen', async ({ page }) => {
        // Nothing here but the reader's key press can end the first jump: no new result is chosen and
        // no other section is opened, so focus must still be in the search box when the jump would land.
        await openSettings(page, { llm_enabled: false });
        await search(page).fill('prompt style');
        await page.keyboard.press('Enter');
        await search(page).pressSequentially('ga', { delay: 150 });
        await page.waitForTimeout(3500);
        await expect(search(page)).toBeFocused();
        await expect(search(page)).toHaveValue('ga');
        await expect(found(page)).toHaveCount(0);
        await expect(page.locator('[data-settings-found-note]')).toHaveCount(0);
        await expect(page.locator('[data-settings-search-note]')).toHaveText('');
    });

    test('a newer choice wins: the earlier one says nothing when it ends', async ({ page }) => {
        await openSettings(page, { llm_enabled: false });
        await search(page).fill('prompt style');
        await page.keyboard.press('Enter');
        await search(page).fill('gap');
        await page.keyboard.press('Enter');
        await expect(page.locator('#visit-gap-seconds')).toBeFocused();
        await page.waitForTimeout(2500);
        await expect(page.locator('#visit-gap-seconds')).toBeFocused();
        await expect(page.locator('[data-settings-search-note]')).toHaveText('');
        await expect(page.locator('[data-settings-found-note]')).toHaveCount(0);
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
        await openSettings(page, EVERYTHING_ON, { respond: SERVICES_ANSWER });
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
            // Chosen through the box, as a reader would, by its own label.
            const label = labelOf(entry.labelKey);
            await box.fill(label);
            const option = page.locator(`[data-settings-search-option="${entry.anchor}"]`);
            if ((await option.count()) === 0) {
                missed.push(`${entry.anchor}: not offered for its own label "${label}"`);
                continue;
            }
            await option.click();
            const landed = await expect.poll(() => focusIsOn(page, entry.anchor, entry.kind === 'group'), { timeout: 10_000 }).toBe(true).then(() => true, () => false);
            if (!landed) {
                const where = await page.evaluate(() => document.activeElement?.id || document.activeElement?.tagName || '');
                missed.push(`${entry.anchor}: focus went to ${where}`);
                continue;
            }
            // A group's heading is one level down under More options: an h4 there, an h3 otherwise.
            if (entry.kind === 'group') {
                const tag = await page.evaluate(() => document.activeElement?.tagName ?? '');
                const expected = settingsSearchInMore(entry) ? 'H4' : 'H3';
                if (tag !== expected) missed.push(`${entry.anchor}: its heading is ${tag}, and it ${expected === 'H4' ? 'is' : 'is not'} under More options`);
            }
        }
        expect(missed).toEqual([]);
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

    test('the reason a result opened a switch is on screen beside that switch, not scrolled away with the search', async ({ page }) => {
        await openSettings(page, { llm_enabled: false });
        await search(page).fill('prompt style');
        await results(page).first().click();
        const aiSwitch = page.getByRole('switch', { name: /AI/ }).first();
        await expect(aiSwitch).toBeFocused({ timeout: 15_000 });
        const beside = page.locator('[data-settings-found-note]');
        await expect(beside).toHaveText(/is shown once/);
        await expect.poll(async () => {
            const [note, toggle] = [await beside.boundingBox(), await aiSwitch.boundingBox()];
            return Boolean(note && toggle && note.y >= 0 && note.y + note.height <= 844 && toggle.y >= 0 && toggle.y + toggle.height <= 844);
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
