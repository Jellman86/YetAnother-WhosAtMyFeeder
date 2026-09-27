import { describe, expect, it } from 'vitest';
import settingsSource from '../pages/Settings.svelte?raw';
import appSource from '../../App.svelte?raw';
import dialogSource from './ConfirmDialog.svelte?raw';

const sources = import.meta.glob(['../**/*.svelte', '../**/*.ts', '!../**/*.test.ts'], {
    eager: true,
    query: '?raw',
    import: 'default'
}) as Record<string, string>;

const codeOnly = (source: string) => source.replace(/\/\/.*$/gm, '').replace(/\/\*[\s\S]*?\*\//g, '');

function handler(source: string, name: string): string {
    const start = source.indexOf(`async function ${name}(`);
    expect(start, `${name} exists`).toBeGreaterThan(-1);
    const next = source.indexOf('\n    async function ', start + 1);
    return source.slice(start, next === -1 ? undefined : next);
}

describe('destructive actions ask in the app, never through the browser', () => {
    it('uses no native confirm, alert or prompt, which embedded browsers silently suppress', () => {
        // In the desktop app's browser a native confirm() returned false without showing,
        // so "Reset Database & Cache" did nothing and said nothing.
        const offenders = Object.entries(sources)
            .filter(([, source]) => /(^|[^\w.])(window\.)?(confirm|alert|prompt)\(/m.test(codeOnly(source)))
            .map(([path]) => path);
        expect(offenders).toEqual([]);
    });

    it('mounts one confirmation dialog that cancels safely', () => {
        expect(appSource).toContain('<ConfirmDialog />');
        expect(dialogSource).toContain('role="alertdialog"');
        expect(dialogSource).toContain('aria-modal="true"');
        expect(dialogSource).toContain('trapFocus(dialogEl)');
        expect(dialogSource).toContain("event.key !== 'Escape'");
        // Cancel precedes the destructive button, so initial focus is the safe answer.
        expect(dialogSource.indexOf("$_('common.cancel')")).toBeLessThan(dialogSource.indexOf('pending.confirmLabel'));
    });

    it.each([
        ['handleCacheCleanup', 'settings.data.cache_cleanup_confirm'],
        ['handleCleanup', 'settings.data.purge_confirm'],
        ['handleResetDatabase', 'settings.danger.reset_button'],
        ['handleClearFavorites', 'settings.data.clear_favorites_confirm'],
        ['handleClearFeedback', 'settings.danger.clear_feedback_button'],
        ['handlePurgeMissingMedia', 'settings.data.purge_missing_media_confirm']
    ])('%s asks before it deletes anything', (name, key) => {
        const body = handler(settingsSource, name);
        const asked = body.indexOf('await confirmAction(');
        expect(asked, `${name} confirms`).toBeGreaterThan(-1);
        expect(body).toContain(key);
        expect(body.indexOf('if (!confirmed)')).toBeGreaterThan(asked);
    });

    it('purging with unlimited retention skips the question, since nothing would be deleted', () => {
        const body = handler(settingsSource, 'handleCleanup');
        expect(body).toContain('if (days > 0)');
    });
});
