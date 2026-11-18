import { beforeAll, describe, expect, it } from 'vitest';
import { addMessages, init, locale } from 'svelte-i18n';

import deCommon from '../i18n/locales/de/common.json';
import enCommon from '../i18n/locales/en/common.json';
import { newBirdAnnouncement } from './live-announcement';

describe('what a screen reader hears when a bird arrives', () => {
    beforeAll(async () => {
        addMessages('en', { common: enCommon });
        addMessages('de', { common: deCommon });
        await init({ fallbackLocale: 'en', initialLocale: 'en' });
    });

    it('names the bird and the camera, without the internal word "detected"', async () => {
        await locale.set('en');
        expect(newBirdAnnouncement('Blue Tit', 'Feeder')).toBe('New bird: Blue Tit at Feeder');
    });

    it('is spoken in the page’s language', async () => {
        await locale.set('de');
        const german = newBirdAnnouncement('Blaumeise', 'Futterhaus');
        expect(german).toContain('Blaumeise');
        expect(german).toContain('Futterhaus');
        expect(german).not.toContain('New bird');
        await locale.set('en');
    });
});
