import { describe, expect, it } from 'vitest';

/**
 * A control character in a translation is invisible in an editor and shows as a box, or as
 * nothing, where punctuation was meant: French once read "Réessayez si cela continue" with a
 * U+0001 in place of its semicolon. Every locale file is read as text, so a file added later is
 * held to this without being listed here.
 */
const FILES = import.meta.glob<string>('./locales/*/*.json', { query: '?raw', import: 'default', eager: true });

// C0 and C1 controls and DEL. Tab and newline are the two a string may legitimately hold.
const CONTROL = /[\u0000-\u0008\u000b-\u001f\u007f-\u009f]/;

function codePoint(character: string): string {
    return `U+${character.charCodeAt(0).toString(16).toUpperCase().padStart(4, '0')}`;
}

function controlCharacters(value: unknown, path: string): string[] {
    if (typeof value === 'string') {
        const found = CONTROL.exec(value);
        return found ? [`${path}: ${codePoint(found[0])} in ${JSON.stringify(value)}`] : [];
    }
    if (!value || typeof value !== 'object') return [];
    return Object.entries(value).flatMap(([key, child]) => [
        ...(CONTROL.test(key) ? [`${path}.${key}: a control character in the key`] : []),
        ...controlCharacters(child, path ? `${path}.${key}` : key)
    ]);
}

describe('locale files hold no control characters', () => {
    const files = Object.entries(FILES).sort(([a], [b]) => a.localeCompare(b));

    it('reads every namespace of all nine languages', () => {
        const languages = new Set(files.map(([file]) => file.split('/')[2]));
        expect([...languages].sort()).toEqual(['de', 'en', 'es', 'fr', 'it', 'ja', 'pt', 'ru', 'zh']);
        const perLanguage = files.filter(([file]) => file.startsWith('./locales/en/')).length;
        expect(perLanguage).toBeGreaterThan(20);
        expect(files).toHaveLength(perLanguage * languages.size);
    });

    it.each(files)('%s', (file, text) => {
        // Written raw or as a \u escape, the character ends up in the parsed string either way.
        expect(controlCharacters(JSON.parse(text), '')).toEqual([]);
        // Outside the strings, only the file's own tabs and newlines belong.
        expect(CONTROL.test(text), `${file} has a raw control character`).toBe(false);
    });
});
