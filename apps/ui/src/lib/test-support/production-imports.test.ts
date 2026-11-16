// @ts-nocheck — this source audit runs under Vitest's Node environment; Node types are
// intentionally absent from the browser application tsconfig.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { parse as parseSvelte } from 'svelte/compiler';
import ts from 'typescript';
import { describe, expect, it } from 'vitest';

/**
 * `test-support` states claims the application must earn (`asGuarded` brands any promise as a
 * guarded read), so no source the app is built from may import it: only tests and other test
 * support. A test file is named `*.test.ts` or `*.spec.ts`; everything else under `src` can be
 * reached from `main.ts`, and is checked here.
 *
 * Sources are parsed, not searched, so comments and formatting cannot hide an import. Every
 * module reference is collected: static imports and re-exports, `import(…)`, `require(…)`,
 * `import x = require(…)`, `typeof import(…)` and `import.meta.glob(…)`. A reference whose target
 * is not a literal cannot be checked, and is refused as well.
 */
const SRC = join(process.cwd(), 'src');
const TEST_SUPPORT = join(SRC, 'lib', 'test-support');
const TEST_FILE = /\.(test|spec)\.ts$/;

/** A module reference: its literal text, or null when it is computed and cannot be checked. */
type Reference = string | null;

function literalText(node: ts.Node | undefined): Reference {
    if (node && (ts.isStringLiteral(node) || ts.isNoSubstitutionTemplateLiteral(node))) return node.text;
    return null;
}

function isImportMetaGlob(call: ts.CallExpression): boolean {
    const callee = call.expression;
    return (
        ts.isPropertyAccessExpression(callee) &&
        callee.name.text === 'glob' &&
        ts.isMetaProperty(callee.expression) &&
        callee.expression.keywordToken === ts.SyntaxKind.ImportKeyword
    );
}

/** Every module a TypeScript or JavaScript source refers to. */
function scriptReferences(source: string, fileName: string): Reference[] {
    const file = ts.createSourceFile(fileName, source, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS);
    const found: Reference[] = [];
    const visit = (node: ts.Node): void => {
        if ((ts.isImportDeclaration(node) || ts.isExportDeclaration(node)) && node.moduleSpecifier) {
            found.push(literalText(node.moduleSpecifier));
        } else if (ts.isImportEqualsDeclaration(node) && ts.isExternalModuleReference(node.moduleReference)) {
            found.push(literalText(node.moduleReference.expression));
        } else if (ts.isImportTypeNode(node)) {
            found.push(ts.isLiteralTypeNode(node.argument) ? literalText(node.argument.literal) : null);
        } else if (ts.isCallExpression(node)) {
            const dynamicImport = node.expression.kind === ts.SyntaxKind.ImportKeyword;
            const require = ts.isIdentifier(node.expression) && node.expression.text === 'require';
            if (dynamicImport || require) {
                found.push(literalText(node.arguments[0]));
            } else if (isImportMetaGlob(node)) {
                const patterns = node.arguments[0];
                if (patterns && ts.isArrayLiteralExpression(patterns)) found.push(...patterns.elements.map((element) => literalText(element)));
                else found.push(literalText(patterns));
            }
        }
        ts.forEachChild(node, visit);
    };
    visit(file);
    return found;
}

/** A Svelte file's `<script>` blocks are scripts; its markup can hold `import(…)` too. */
function svelteReferences(source: string, fileName: string): Reference[] {
    const ast = parseSvelte(source, { modern: true, filename: fileName });
    const found: Reference[] = [];
    for (const script of [ast.instance, ast.module]) {
        if (script) found.push(...scriptReferences(source.slice(script.content.start, script.content.end), fileName));
    }
    const visit = (node: unknown): void => {
        if (!node || typeof node !== 'object') return;
        if (Array.isArray(node)) {
            node.forEach(visit);
            return;
        }
        const record = node as { type?: string; source?: { type?: string; value?: unknown; expressions?: unknown[]; quasis?: { value: { cooked: string } }[] } };
        if (record.type === 'ImportExpression') {
            const target = record.source;
            if (target?.type === 'Literal' && typeof target.value === 'string') found.push(target.value);
            else if (target?.type === 'TemplateLiteral' && target.expressions?.length === 0) found.push(target.quasis?.[0]?.value.cooked ?? null);
            else found.push(null);
        }
        for (const [key, value] of Object.entries(node)) {
            if (key !== 'instance' && key !== 'module') visit(value);
        }
    };
    visit(ast.fragment);
    return found;
}

function references(source: string, fileName: string): Reference[] {
    return fileName.endsWith('.svelte') ? svelteReferences(source, fileName) : scriptReferences(source, fileName);
}

/** Why a reference may not appear in application code, or null when it may. */
function refusal(reference: Reference, fileName: string): string | null {
    if (reference === null) return 'a module reference that is not a literal cannot be checked';
    if (reference.includes('test-support')) return `imports test support (${reference})`;
    if (reference.startsWith('.') && resolve(dirname(fileName), reference).startsWith(TEST_SUPPORT)) return `imports test support (${reference})`;
    if (reference.includes('**')) return `a recursive glob could reach test support (${reference})`;
    return null;
}

function sources(dir: string): string[] {
    return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const path = join(dir, entry.name);
        if (entry.isDirectory()) return path === TEST_SUPPORT ? [] : sources(path);
        return /\.(ts|js|svelte)$/.test(entry.name) && !TEST_FILE.test(entry.name) ? [path] : [];
    });
}

function offenders(source: string, fileName: string): string[] {
    return references(source, fileName).flatMap((reference) => refusal(reference, fileName) ?? []);
}

describe('test support stays out of the application', () => {
    it('finds the sources it checks', () => {
        expect(sources(SRC).map((path) => relative(SRC, path))).toEqual(expect.arrayContaining(['main.ts', 'App.svelte']));
    });

    it('is imported by no application source', () => {
        const found = sources(SRC).flatMap((path) => offenders(readFileSync(path, 'utf8'), path).map((why) => `${relative(SRC, path)}: ${why}`));
        expect(found).toEqual([]);
    });

    const fixture = join(SRC, 'lib', 'copied-fixture.ts');
    it.each([
        ['a static import', "import { asGuarded } from '../lib/test-support/guarded';"],
        ['an alias', 'import { asGuarded } from "$lib/test-support/guarded";'],
        ['a side-effect import', "import './test-support/guarded';"],
        ['a re-export with a comment before its source', "export { asGuarded } from /* helper */ './test-support/guarded';"],
        ['a re-export of everything', "export * from './test-support/guarded';"],
        ['a dynamic import with a comment inside', "const helper = await import(/* lazy */ './test-support/guarded');"],
        ['a dynamic import with a template literal', 'const helper = await import(`./test-support/guarded`);'],
        ['a dynamic import with a computed path', "const helper = await import('./test-' + 'support/guarded');"],
        ['a dynamic import of a variable', 'const where = "./x"; const helper = await import(where);'],
        ['a path that climbs back into it', "import { asGuarded } from './../lib/./test-support/guarded';"],
        ['a type-only import', "import type { Guarded } from './test-support/guarded';"],
        ['an import type', "type Helper = typeof import('./test-support/guarded');"],
        ['a require', "const helper = require('./test-support/guarded');"],
        ['a recursive glob', "const all = import.meta.glob('./**/*.ts');"]
    ])('refuses %s', (_name, line) => {
        expect(offenders(line, fixture)).not.toEqual([]);
    });

    it('refuses the same in a Svelte script and in its markup', () => {
        const component = join(SRC, 'lib', 'CopiedFixture.svelte');
        const inScript = '<script lang="ts">\n    import { asGuarded } from /* c */ "./test-support/guarded";\n    const n: number = 1;\n</script>\n<p>{n}</p>';
        const inModuleScript = '<script module lang="ts">\n    export { asGuarded } from "./test-support/guarded";\n</script>';
        const inMarkup = '{#await import(`./test-support/guarded`) then helper}<p>{helper}</p>{/await}';
        for (const source of [inScript, inModuleScript, inMarkup]) expect(offenders(source, component)).not.toEqual([]);
    });

    it('lets ordinary imports through', () => {
        expect(offenders("import { apiFetchJson } from './api/core';\nconst page = () => import('./pages/Errors.svelte');\nconst locales = import.meta.glob('./locales/*.ts');", fixture)).toEqual([]);
    });
});
