// @ts-nocheck — this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

/**
 * `test-support` states claims the application must earn (`asGuarded` brands any promise as a
 * guarded read), so no source the app is built from may import it: only tests and other test
 * support. A test file is named `*.test.ts` or `*.spec.ts`; everything else under `src` can be
 * reached from `main.ts`, and is checked here.
 */
const SRC = join(process.cwd(), 'src');
const TEST_FILE = /\.(test|spec)\.ts$/;
const IMPORTS_TEST_SUPPORT = /(?:from\s*|import\s*\(\s*|import\s+)['"][^'"]*test-support[^'"]*['"]/;

function sources(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) return entry.name === 'test-support' ? [] : sources(path);
        return /\.(ts|js|svelte)$/.test(entry.name) && !TEST_FILE.test(entry.name) ? [path] : [];
    });
}

describe('test support stays out of the application', () => {
    it('finds the sources it checks', () => {
        expect(sources(SRC).map((path) => relative(SRC, path))).toContain('main.ts');
    });

    it('is imported by no application source', () => {
        const offenders = sources(SRC)
            .filter((path) => IMPORTS_TEST_SUPPORT.test(readFileSync(path, 'utf8')))
            .map((path) => relative(SRC, path));
        expect(offenders).toEqual([]);
    });

    it('recognises each way of importing it', () => {
        for (const line of [
            "import { asGuarded } from '../test-support/guarded';",
            'import { asGuarded } from "$lib/test-support/guarded";',
            "const helper = await import('./lib/test-support/guarded');",
            "import './lib/test-support/guarded';"
        ]) {
            expect(IMPORTS_TEST_SUPPORT.test(line)).toBe(true);
        }
    });
});
