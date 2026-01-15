import { register, init, locale, _, addMessages, getLocaleFromNavigator } from 'svelte-i18n';
import en from './locales/en.json';

// Synchronously load default locale
addMessages('en', en);

// Register other locales for lazy loading
register('es', () => import('./locales/es.json'));
register('fr', () => import('./locales/fr.json'));
register('de', () => import('./locales/de.json'));
register('ja', () => import('./locales/ja.json'));
register('zh', () => import('./locales/zh.json'));

// Detect browser locale with fallback
const savedLocale = localStorage.getItem('preferred-language');
const browserLocale = savedLocale || getLocaleFromNavigator() || 'en';
// Normalize: 'en-US' -> 'en', 'zh-CN' -> 'zh'
const normalizedLocale = browserLocale.split('-')[0];
// Validate: only use if we support it
const supportedLocales = ['en', 'es', 'fr', 'de', 'ja', 'zh'];
const initialLocale = supportedLocales.includes(normalizedLocale) ? normalizedLocale : 'en';

init({
    fallbackLocale: 'en',
    initialLocale,
});

export { locale, _ };
