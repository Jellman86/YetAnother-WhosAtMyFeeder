import { register, init, locale, _ } from 'svelte-i18n';

// Register locales
register('en', () => import('./locales/en.json'));
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
