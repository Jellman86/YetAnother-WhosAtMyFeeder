import { describe, expect, it } from 'vitest';
import dialogSource from './DiagnosticDialog.svelte?raw';

describe('the shared diagnostic dialog', () => {
    it('announces one status line instead of the whole re-rendering body', () => {
        // The checklist re-renders on every 350 ms reveal tick; a live body repeated it each time.
        expect(dialogSource).not.toContain('aria-live');
        expect(dialogSource.match(/role="status"/g)).toHaveLength(1);
        expect(dialogSource).toContain('<p class="sr-only" role="status">{statusText}</p>');
    });

    it('leaves focus restoration to trapFocus alone', () => {
        expect(dialogSource).toContain('trapFocus(modalElement)');
        expect(dialogSource).not.toContain('previouslyFocused');
        expect(dialogSource).not.toMatch(/\.focus\(\)/);
    });

    it('points aria-describedby at a subtitle only when there is one', () => {
        expect(dialogSource).toContain("aria-describedby={subtitle ? 'diagnostic-description' : undefined}");
        expect(dialogSource).not.toContain('aria-describedby="diagnostic-description"');
    });

    it('gives both footer buttons a 44px target', () => {
        const footer = dialogSource.slice(dialogSource.indexOf('<footer'));
        expect(footer.match(/class="btn [^"]*min-h-11/g)).toHaveLength(2);
    });

    it('stops the reveal timer once the run is over and every stage is on show', () => {
        expect(dialogSource).toContain('if (!busy && tick >= stages.length) clearInterval(timer);');
    });
});
