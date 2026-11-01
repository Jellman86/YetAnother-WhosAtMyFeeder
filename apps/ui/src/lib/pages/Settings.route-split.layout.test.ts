import { describe, expect, it } from 'vitest';

// Route behaviour is tested in ../settings/settings-route.test.ts and, through the real App
// shell, in browser-tests/settings-route.spec.ts. This file keeps the project-wide prohibition.
const allUiSources = import.meta.glob<string>(
    [
        '/src/**/*.svelte',
        '/src/**/*.ts',
        '!/src/**/*.test.ts'
    ],
    { eager: true, query: '?raw', import: 'default' }
);

describe('settings deep links', () => {
    it('no source file under apps/ui/src emits the legacy /settings#<tab> form', () => {
        // Any future feature that adds a hash-form deep link trips this check; the
        // normaliser still accepts the legacy form from old bookmarks.
        const offenders: string[] = [];
        for (const [path, content] of Object.entries(allUiSources)) {
            if (!/['"`]\/settings#[a-z][a-z_-]*/.test(content)) continue;
            offenders.push(path);
        }
        expect(offenders).toEqual([]);
    });
});
