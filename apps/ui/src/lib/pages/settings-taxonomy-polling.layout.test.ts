import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';

function between(source: string, start: string, end: string): string {
    const from = source.indexOf(start);
    expect(from, start).toBeGreaterThan(-1);
    return source.slice(from, source.indexOf(end, from + start.length));
}

describe('taxonomy repair status', () => {
    it('reads the status when the Data tab opens instead of polling every 3 s while it stays open', () => {
        const tabEffect = between(settingsSource, "if (activeTab === 'data') {", '} else {');
        expect(tabEffect).toContain('loadTaxonomyStatus()');
        expect(tabEffect).not.toContain('startTaxonomyPolling()');
    });

    it('polls while a repair runs and for a bounded grace period after starting one', () => {
        const load = between(settingsSource, 'async function loadTaxonomyStatus()', 'async function loadVersion()');
        expect(load).toContain('startTaxonomyPolling()');
        expect(load).toContain('Date.now() >= taxonomyAwaitingStartUntil');
        const start = between(settingsSource, 'async function handleStartTaxonomySync()', 'async function handlePreviewTimezoneRepair()');
        expect(start).toContain('taxonomyAwaitingStartUntil = Date.now() + TAXONOMY_START_GRACE_MS');
        expect(start).toContain('startTaxonomyPolling()');
    });
});
