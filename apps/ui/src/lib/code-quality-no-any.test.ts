// @ts-nocheck — this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync } from 'node:fs';
import { extname, join } from 'node:path';
import { describe, expect, it } from 'vitest';

const SOURCE_ROOT = join(process.cwd(), 'src');
const SOURCE_EXTENSIONS = new Set(['.ts', '.svelte']);
const EXCLUDED_PATH_PARTS = ['/generated/', '.test.ts'];
const EXPLICIT_ANY_PATTERNS = [
    /:\s*any\b/g,
    /\bas\s+any\b/g,
    /<any>/g,
    /\bany\[\]/g,
    /Record<string,\s*any>/g,
    /Promise<any>/g,
];

function sourceFiles(directory: string): string[] {
    return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
        const path = join(directory, entry.name);
        if (entry.isDirectory()) return sourceFiles(path);
        if (!SOURCE_EXTENSIONS.has(extname(entry.name))) return [];
        const normalized = path.replaceAll('\\', '/');
        return EXCLUDED_PATH_PARTS.some((part) => normalized.includes(part)) ? [] : [path];
    });
}

describe('frontend code-quality contract', () => {
    it('does not allow explicit any in application source', () => {
        const violations = sourceFiles(SOURCE_ROOT).flatMap((path) => {
            const source = readFileSync(path, 'utf8');
            return EXPLICIT_ANY_PATTERNS.flatMap((pattern) =>
                [...source.matchAll(pattern)].map((match) => {
                    const line = source.slice(0, match.index).split('\n').length;
                    return `${path.replace(`${process.cwd()}/`, '')}:${line}: ${match[0]}`;
                })
            );
        });

        expect(violations, violations.join('\n')).toEqual([]);
    });
});
