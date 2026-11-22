import { describe, expect, it } from 'vitest';
// @ts-expect-error -- node:fs resolves at runtime, not in the app tsconfig
import { readFileSync } from 'node:fs';
import app from '../../App.svelte?raw';
import { PHONE_SHELL_QUERY } from './shell-breakpoint';

// Read from disk: a stylesheet imported with ?raw is empty under the test runner.
const css: string = readFileSync(new URL('../../app.css', import.meta.url), 'utf8');

describe('PHONE_SHELL_QUERY', () => {
    it("is exactly the complement of Tailwind's md, so no width (a zoomed 767.5 px included) is in neither", () => {
        const md = /--breakpoint-md:\s*([^;]+);/.exec(css)?.[1]?.trim();
        expect(md).toBe('768px');
        expect(PHONE_SHELL_QUERY).toBe(`(width < ${md})`);
    });

    it('is the query the shell follows for its phone form', () => {
        expect(app).toContain('window.matchMedia(PHONE_SHELL_QUERY)');
        expect(app).not.toContain("'(max-width: 767px)'");
    });
});
