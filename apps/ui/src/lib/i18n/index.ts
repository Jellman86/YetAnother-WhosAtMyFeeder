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

init({
    fallbackLocale: 'en',
    initialLocale: 'en',
});

export { locale, _ };
