import { beforeAll, describe, expect, it } from 'vitest';
import { addMessages, format, init, locale } from 'svelte-i18n';
import { get } from 'svelte/store';

import enDashboard from '../i18n/locales/en/dashboard.json';
import deDashboard from '../i18n/locales/de/dashboard.json';

/**
 * Naming an Unknown bird can join it to a visit of its species, so Visits can fall while no capture
 * is lost (#1096). The Visits figure counts its Unknown birds in one line and gives the reason on
 * hover, focus or tap; the browser tests check how it opens.
 */
describe('the Visits figure says how many visits are Unknown birds and why Visits can fall', () => {
    beforeAll(async () => {
        addMessages('en', { dashboard: enDashboard });
        addMessages('de', { dashboard: deDashboard });
        await init({ fallbackLocale: 'en', initialLocale: 'en' });
    });

    it('counts the Unknown birds in a few words that fit one line', async () => {
        await locale.set('en');
        const t = get(format);
        expect(t('dashboard.day_bar.visits_unknown_short', { values: { count: 1 } })).toBe('1 Unknown bird');
        expect(t('dashboard.day_bar.visits_unknown_short', { values: { count: 4 } })).toBe('4 Unknown birds');
    });

    it('explains that a named Unknown bird can join a visit, so Visits can fall, and that no capture is removed', async () => {
        await locale.set('en');
        const t = get(format);
        expect(t('dashboard.day_bar.visits_unknown', { values: { count: 3 } })).toBe(
            '3 of these visits are Unknown birds. An Unknown bird is usually its own visit. Once it is named, by the model or by hand, ' +
                'it can join a visit of the same species on the same camera within the visit gap, so Visits can fall. No capture is removed.'
        );
        expect(t('dashboard.day_bar.visits_unknown', { values: { count: 1 } })).toMatch(/^1 of these visits is an Unknown bird\. /);
    });

    it('says the same in German', async () => {
        await locale.set('de');
        const t = get(format);
        expect(t('dashboard.day_bar.visits_unknown_short', { values: { count: 2 } })).toBe('2 Unbekannte Vögel');
        expect(t('dashboard.day_bar.visits_unknown', { values: { count: 2 } })).toMatch(
            /^2 dieser Besuche sind Unbekannte Vögel\. .*Deshalb können die Besuche sinken\. Keine Aufnahme wird entfernt\.$/
        );
        await locale.set('en');
    });
});
