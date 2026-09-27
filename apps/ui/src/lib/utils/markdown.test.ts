import { describe, expect, it } from 'vitest';
import { renderMarkdown } from './markdown';

describe('renderMarkdown', () => {
    it('preserves bare-domain links across the markdown-it 15 upgrade', () => {
        expect(renderMarkdown('Read example.org for details.')).toContain(
            '<a href="http://example.org">example.org</a>'
        );
    });

    it('keeps embedded HTML escaped', () => {
        expect(renderMarkdown('<script>alert(1)</script>')).not.toContain('<script>');
    });

    it('bounds unmatched smart-quote openers in long analysis text', () => {
        // markdown-it 15.0.2 leaves excessive unmatched openers literal. Check
        // that deterministic safety contract, not a machine-dependent time limit.
        const rendered = renderMarkdown('"bird '.repeat(1500) + ' bird"'.repeat(1500));
        expect(rendered).not.toMatch(/[“”]/);
        expect(rendered.match(/&quot;/g)).toHaveLength(3000);
    });

    it('preserves readable quotes and code in ordinary analysis', () => {
        const rendered = renderMarkdown('The bird called "hello" and the sample was `"unchanged"`.');
        expect(rendered).toContain('“hello”');
        expect(rendered).toContain('<code>&quot;unchanged&quot;</code>');
    });

    it('does not turn unsafe markdown links into executable anchors', () => {
        for (const url of ['javascript:alert(1)', 'data:text/html;base64,PHNjcmlwdD4=']) {
            expect(renderMarkdown(`[Details](${url})`)).not.toContain('<a ');
        }
    });
});
