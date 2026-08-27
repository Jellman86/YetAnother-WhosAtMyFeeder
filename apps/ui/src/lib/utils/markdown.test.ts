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
});
