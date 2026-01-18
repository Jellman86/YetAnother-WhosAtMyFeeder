import { init, locale, _, addMessages } from 'svelte-i18n';
import en from './locales/en.json';
import es from './locales/es.json';
import fr from './locales/fr.json';
import de from './locales/de.json';
import ja from './locales/ja.json';
import zh from './locales/zh.json';

const appVersion = typeof __APP_VERSION__ === 'string' ? __APP_VERSION__ : 'unknown';
console.log(`Running YA-WAMF ${appVersion}`);

const supportedLocales = ['en', 'es', 'fr', 'de', 'ja', 'zh'];

function normalizeLocale(value: unknown): string | null {
    if (typeof value !== 'string') {
        return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
        return null;
    }
    const base = trimmed.split(/[-_]/)[0].toLowerCase();
    return supportedLocales.includes(base) ? base : null;
}

function determineLocale(): string {
    let candidate: string | null = null;
    try {
        candidate = normalizeLocale(localStorage.getItem('preferred-language'));
    } catch {
        // localStorage may be unavailable in some contexts.
    }

    if (!candidate && typeof navigator !== 'undefined') {
        const navLang = Array.isArray(navigator.languages)
            ? navigator.languages[0]
            : navigator.language;
        candidate = normalizeLocale(navLang);
    }

    if (!candidate) {
        console.warn('[i18n] Could not determine a valid locale; falling back to en');
        return 'en';
    }
    return candidate;
}

// Synchronously load all locales
addMessages('en', en);
addMessages('es', es);
addMessages('fr', fr);
addMessages('de', de);
addMessages('ja', ja);
addMessages('zh', zh);

const initialLocale = determineLocale();
// Ensure locale store is always a string before any translations run.
locale.set(initialLocale);

init({
    fallbackLocale: 'en',
    initialLocale,
});

export { locale, _ };
