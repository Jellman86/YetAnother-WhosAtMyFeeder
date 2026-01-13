import { register, init, getLocaleFromNavigator, locale, _ } from 'svelte-i18n';

// Register locales
register('en', () => import('./locales/en.json'));
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));
register('ja', () => import('./locales/ja.json'));

// Initialize with browser locale or fallback to English
const supportedLocales = ['en', 'es', 'fr', 'de', 'ja'];
let detected = getLocaleFromNavigator();

// Normalize locale (e.g. "en-US" -> "en")
if (detected) {
    // Take the first part of the locale string (e.g. "en" from "en-US")
    const langCode = detected.split('-')[0].split('@')[0];
    if (supportedLocales.includes(langCode)) {
        detected = langCode;
    } else {
        detected = 'en';
    }
} else {
    detected = 'en';
}

init({
    fallbackLocale: 'en',
    initialLocale: detected,
});

export { locale, _ };
