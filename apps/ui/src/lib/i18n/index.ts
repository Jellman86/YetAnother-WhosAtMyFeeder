import { register, init, locale, _, addMessages, getLocaleFromNavigator } from 'svelte-i18n';
import en from './locales/en.json';

console.log('YA-WAMF i18n module initialized - Debug Beacon 2026-01-17T12:00:00Z');

// Synchronously load default locale
addMessages('en', en);

// Register other locales for lazy loading
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));
register('ja', () => import('./locales/ja.json'));
register('zh', () => import('./locales/zh.json'));

// Function to robustly determine the initial locale
function determineLocale(): string {
    const savedLocale = localStorage.getItem('preferred-language');
    if (savedLocale && typeof savedLocale === 'string') {
        return savedLocale;
    }

    const browserLocale = getLocaleFromNavigator();
    if (browserLocale && typeof browserLocale === 'string') {
        return browserLocale;
    }

    // This warning helps debug future issues with locale detection.
    console.warn(
        `[i18n] Could not determine a valid locale from storage or browser. Falling back to 'en'. Received:`,
        { savedLocale, browserLocale },
    );
    return 'en';
}

// Detect browser locale with robust fallback
const rawLocale = determineLocale();
// Normalize: 'en-US' -> 'en', 'zh-CN' -> 'zh'
const normalizedLocale = rawLocale.split('-')[0];
// Validate: only use if we support it, otherwise fallback to 'en'
const supportedLocales = ['en', 'es', 'fr', 'de', 'ja', 'zh'];
const initialLocale = supportedLocales.includes(normalizedLocale) ? normalizedLocale : 'en';

init({
    fallbackLocale: 'en',
    initialLocale,
});

export { locale, _ };
