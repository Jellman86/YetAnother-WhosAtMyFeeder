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
function determineLocale(): string | null {
    // 1. Check localStorage
    const savedLocale = typeof window !== 'undefined' ? localStorage.getItem('preferred-language') : null;
    if (typeof savedLocale === 'string' && savedLocale.length > 0) {
        return savedLocale;
    }

    // 2. Check browser navigator
    const browserLocale = getLocaleFromNavigator();
    if (typeof browserLocale === 'string' && browserLocale.length > 0) {
        return browserLocale;
    }
    
    return null;
}

// --- Initialization ---

const supportedLocales = ['en', 'es', 'fr', 'de', 'ja', 'zh'];

let initialLocale: string;
const rawLocale = determineLocale();

if (rawLocale) {
    // Normalize: 'en-US' -> 'en', 'zh-CN' -> 'zh'
    const normalizedLocale = rawLocale.split('-')[0];
    // Validate: only use if we support it, otherwise fallback to 'en'
    initialLocale = supportedLocales.includes(normalizedLocale) ? normalizedLocale : 'en';
} else {
    // Fallback if everything else fails
    initialLocale = 'en';
    console.warn(
        `[i18n] Could not determine a valid locale from storage or browser. Falling back to 'en'.`
    );
}


init({
    fallbackLocale: 'en',
    initialLocale: initialLocale,
});

export { locale, _ };
