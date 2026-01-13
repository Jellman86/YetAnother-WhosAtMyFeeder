import { register, init, getLocaleFromNavigator, locale, _ } from 'svelte-i18n';

// Register locales
register('en', () => import('./locales/en.json'));
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));
register('ja', () => import('./locales/ja.json'));

// Initialize with browser locale or fallback to English
init({
    fallbackLocale: 'en',
    initialLocale: getLocaleFromNavigator(),
});

export { locale, _ };
