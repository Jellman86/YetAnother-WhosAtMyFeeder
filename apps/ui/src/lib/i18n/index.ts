import { _, init, locale, register } from 'svelte-i18n';

import { createRetryablePageLoader } from '../app/page-loader';

const SUPPORTED_LOCALES = ['en', 'es', 'fr', 'de', 'ja', 'zh', 'ru', 'pt', 'it'] as const;
type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];
type LocaleModule = { default: Record<string, unknown> };

const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
void appVersion; // version available in diagnostics reports and window.__APP_VERSION__

function normalizeLocale(value: unknown): SupportedLocale | null {
    if (typeof value !== 'string') return null;
    const base = value.trim().split(/[-_]/)[0]?.toLowerCase();
    if (!base) return null;
    return SUPPORTED_LOCALES.find((candidate) => candidate === base) ?? null;
}

function determineLocale(): SupportedLocale {
    let candidate: SupportedLocale | null = null;
    try {
        candidate = normalizeLocale(localStorage.getItem('preferred-language'));
    } catch {
        // Storage can be unavailable in private or embedded browser contexts.
    }

    if (!candidate && typeof navigator !== 'undefined') {
        const browserLanguage = Array.isArray(navigator.languages)
            ? navigator.languages[0]
            : navigator.language;
        candidate = normalizeLocale(browserLanguage);
    }

    return candidate ?? 'en';
}

function registerLocaleWithRetry(
    localeCode: SupportedLocale,
    importLocale: () => Promise<LocaleModule>
): void {
    const loadLocale = createRetryablePageLoader(importLocale);
    const registeredLoader = async (): Promise<LocaleModule> => {
        try {
            return await loadLocale();
        } catch (error: unknown) {
            // svelte-i18n consumes a registered loader before awaiting it. Put it
            // back so a transient network failure can recover on the next choice.
            register(localeCode, registeredLoader);
            throw error;
        }
    };
    register(localeCode, registeredLoader);
}

registerLocaleWithRetry('en', () => import('./locales/en.json'));
registerLocaleWithRetry('es', () => import('./locales/es.json'));
registerLocaleWithRetry('fr', () => import('./locales/fr.json'));
registerLocaleWithRetry('de', () => import('./locales/de.json'));
registerLocaleWithRetry('ja', () => import('./locales/ja.json'));
registerLocaleWithRetry('zh', () => import('./locales/zh.json'));
registerLocaleWithRetry('ru', () => import('./locales/ru.json'));
registerLocaleWithRetry('pt', () => import('./locales/pt.json'));
registerLocaleWithRetry('it', () => import('./locales/it.json'));

const initialLocale = determineLocale();

async function initializeI18n(): Promise<void> {
    try {
        await init({
            fallbackLocale: 'en',
            initialLocale
        });
    } catch (error: unknown) {
        if (initialLocale === 'en') throw error;
        console.warn(`[i18n] Could not load ${initialLocale}; falling back to English.`);
        await locale.set('en');
    }
}

export const i18nReady = initializeI18n();

export async function setAppLocale(value: string): Promise<boolean> {
    const nextLocale = normalizeLocale(value);
    if (!nextLocale) return false;

    try {
        await locale.set(nextLocale);
    } catch (error: unknown) {
        console.error(`[i18n] Could not load ${nextLocale}.`, error);
        return false;
    }

    try {
        localStorage.setItem('preferred-language', nextLocale);
    } catch {
        // The active language still works when embedded/private storage is blocked.
    }
    return true;
}

export { _, locale };
