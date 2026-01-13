import { register, init, locale, _, addMessages } from 'svelte-i18n';
import en from './locales/en.json';

// Synchronously load default locale
addMessages('en', en);

// Register other locales for lazy loading
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));
register('ja', () => import('./locales/ja.json'));

// Hardcode English for now to ensure startup, then we can detect
init({
    fallbackLocale: 'en',
    initialLocale: 'en',
});

export { locale, _ };
