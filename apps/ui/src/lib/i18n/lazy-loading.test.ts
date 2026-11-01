import { describe, expect, it } from 'vitest';

import i18nSource from './index.ts?raw';
import mainSource from '../../main.ts?raw';

describe('translation delivery', () => {
    it('loads each language on demand instead of bundling every language up front', () => {
        expect(i18nSource).not.toMatch(/^import\s[^;]*\.\/locales\//m);
        for (const locale of ['en', 'es', 'fr', 'de', 'ja', 'zh', 'ru', 'pt', 'it']) {
            expect(i18nSource).toContain(`registerLocaleWithRetry('${locale}', () => import('./locales/${locale}'));`);
        }
        expect(i18nSource).toContain("fallbackLocale: 'en'");
    });

    it('waits for the initial locale before mounting the application', () => {
        expect(mainSource).toContain("import { i18nReady } from './lib/i18n'");
        expect(mainSource).toContain('await i18nReady;');
        expect(mainSource.indexOf('await i18nReady;')).toBeLessThan(mainSource.indexOf('mount(App'));
    });
});
