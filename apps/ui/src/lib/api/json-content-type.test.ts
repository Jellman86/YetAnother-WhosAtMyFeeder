import { describe, expect, it } from 'vitest';

const apiModules = import.meta.glob<string>('./*.ts', {
    query: '?raw',
    import: 'default',
    eager: true
});

describe('API JSON requests', () => {
    it('sets a Content-Type header on every apiFetch call that sends JSON.stringify', () => {
        const sources = Object.entries(apiModules).filter(([path]) => !path.endsWith('.test.ts'));
        expect(sources.length).toBeGreaterThan(10);

        const missing: string[] = [];
        for (const [path, source] of sources) {
            for (const match of source.matchAll(/apiFetch\([^;]+?body:\s*JSON\.stringify\([^)]*\)/gs)) {
                if (!/content-type/i.test(match[0])) {
                    const line = source.slice(0, match.index ?? 0).split('\n').length;
                    missing.push(`${path}:${line}`);
                }
            }
        }
        expect(missing).toEqual([]);
    });
});
