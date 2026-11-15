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

    it('names its progress bar after the dialog', () => {
        expect(dialogSource).toMatch(/role="progressbar" aria-labelledby="diagnostic-title"/);
    });

    it('states each outcome once: the summary never repeats a row', () => {
        expect(dialogSource).toContain('{diagnosticHeadline(result, displayStages)}');
        expect(dialogSource).not.toContain('<p class="font-bold">{result.message}</p>');
    });

    it('has one close control, and the run button as the only footer action', () => {
        // The X in the header is the close every dialog uses; a second Close in the footer was a
        // second tab stop for the same thing.
        expect(dialogSource.match(/onclick=\{onClose\}/g)).toHaveLength(1);
        const footer = dialogSource.slice(dialogSource.indexOf('data-diagnostic-actions'));
        expect(footer.match(/class="btn [^"]*min-h-11/g)).toHaveLength(1);
        expect(dialogSource).toContain('{#if onRetry}\n        <div class="flex items-center justify-end');
    });

    it('says a finished run can be run again, rather than repeating the first label', () => {
        expect(dialogSource).toContain("result ? $_('common.test_again', { default: 'Test again' })");
    });

    it('states each stage outcome in a word, so no state is carried by colour alone', () => {
        // A failed and a warned stage shared the same "!" disc and differed only by colour.
        expect(dialogSource).toContain('data-diagnostic-stage-state');
        for (const state of ['passed', 'failed', 'warning', 'skipped']) {
            expect(dialogSource).toContain(`common.diagnostic_state_${state}`);
        }
    });

    it('shows no product eyebrow unless a caller gives one, and no summary that repeats the rows', () => {
        expect(dialogSource).not.toContain("eyebrow = 'YA-WAMF'");
        expect(dialogSource).toContain('{#if eyebrow}');
        // A failure summary is drawn only when it adds something the rows did not say.
        expect(dialogSource).toContain('summaryAddsSomething');
        // Amber is for work that needs a person; a failed check is red, like its row.
        expect(dialogSource).not.toMatch(/data-diagnostic-result[\s\S]{0,400}attention/);
    });

    it('stops the reveal timer once the run is over and every stage is on show', () => {
        expect(dialogSource).toContain('if (!busy && tick >= stages.length) clearInterval(timer);');
    });
});
