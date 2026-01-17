import { init, locale, _, addMessages } from 'svelte-i18n';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import de from './locales/de.json';
import ja from './locales/ja.json';
import zh from './locales/zh.json';

console.log('YA-WAMF i18n module initialized - Debug Beacon 2026-01-17T12:00:00Z');

// Synchronously load all locales
addMessages('en', en);
addMessages('es', es);
addMessages('fr', fr);
addMessages('de', de);
addMessages('ja', ja);
addMessages('zh', zh);

init({
    fallbackLocale: 'en',
    initialLocale: 'en',
});

export { locale, _ };
