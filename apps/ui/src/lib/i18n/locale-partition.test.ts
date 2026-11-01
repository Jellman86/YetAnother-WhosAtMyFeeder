import { describe, expect, it } from 'vitest';

import { dictionaryFromDomainFiles, SUPPORTED_LOCALES } from './locale-partition';

const authoredSources = import.meta.glob<string>('./locales/**/*', {
    eager: true,
    query: '?raw',
    import: 'default'
});

/** Returns the keys a JSON text repeats inside one object; `JSON.parse` would keep only the last. */
function repeatedKeys(text: string): string[] {
    const repeated: string[] = [];
    const objects: Array<Set<string> | null> = [];
    let expectingKey = false;
    let index = 0;
    while (index < text.length) {
        const character = text[index];
        if (character === '"') {
            let end = index + 1;
            while (text[end] !== '"') end += text[end] === '\\' ? 2 : 1;
            const current = objects[objects.length - 1];
            if (expectingKey && current) {
                const key = JSON.parse(text.slice(index, end + 1)) as string;
                if (current.has(key)) repeated.push(key);
                current.add(key);
                expectingKey = false;
            }
            index = end + 1;
            continue;
        }
        if (character === '{') {
            objects.push(new Set());
            expectingKey = true;
        } else if (character === '[') {
            objects.push(null);
        } else if (character === '}' || character === ']') {
            objects.pop();
        } else if (character === ',') {
            expectingKey = objects[objects.length - 1] !== null;
        }
        index += 1;
    }
    return repeated;
}

const DOMAIN_FILE = /^\.\/locales\/([a-z]{2})\/([a-z][a-z0-9_]*)\.json$/;
const LANGUAGE_MODULE = /^\.\/locales\/([a-z]{2})\.ts$/;

function domainFiles(language: string): string[] {
    return Object.keys(authoredSources)
        .flatMap((path) => {
            const file = DOMAIN_FILE.exec(path);
            return file && file[1] === language ? [file[2]] : [];
        })
        .sort();
}

describe('locale partition', () => {
    it('joins domain files into one dictionary keyed by file name', () => {
        const settings = { title: 'Settings' };
        const garden = { title: 'Garden' };

        expect(dictionaryFromDomainFiles({ './de/settings.json': settings, './de/garden.json': garden })).toEqual({
            settings,
            garden
        });
        expect(() => dictionaryFromDomainFiles({ './de/Settings-new.json': settings })).toThrow(/<domain>\.json/);
    });

    it('authors only language modules and their domain files, so the loader reads every file', () => {
        const unread = Object.keys(authoredSources).filter((path) => {
            const language = DOMAIN_FILE.exec(path)?.[1] ?? LANGUAGE_MODULE.exec(path)?.[1];
            return !language || !(SUPPORTED_LOCALES as readonly string[]).includes(language);
        });
        expect(unread).toEqual([]);
        for (const language of SUPPORTED_LOCALES) {
            expect(authoredSources[`./locales/${language}.ts`], `${language} language module`).toContain(
                `import.meta.glob<LocaleDictionary>('./${language}/*.json'`
            );
        }
    });

    it('gives every language the same domain files as English', () => {
        expect(domainFiles('en').length).toBeGreaterThan(0);
        for (const language of SUPPORTED_LOCALES) {
            expect(domainFiles(language), `${language} domain files`).toEqual(domainFiles('en'));
        }
    });

    it('authors each domain as one JSON object that repeats no key', () => {
        for (const [path, source] of Object.entries(authoredSources)) {
            if (!DOMAIN_FILE.test(path)) continue;
            const parsed: unknown = JSON.parse(source);
            expect(parsed !== null && typeof parsed === 'object' && !Array.isArray(parsed), `${path} holds an object`).toBe(true);
            expect(repeatedKeys(source), `${path} repeats keys`).toEqual([]);
        }
    });

    it('detects a key repeated in the same object, and only there', () => {
        expect(repeatedKeys('{"a": "1", "b": {"a": "2"}, "a": "3"}')).toEqual(['a']);
        expect(repeatedKeys('{"a": ["a", "a"], "b": {"c": "\\"a\\""}}')).toEqual([]);
    });
});
