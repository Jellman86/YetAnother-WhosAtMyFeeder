import { describe, expect, it } from 'vitest';

import audioHistorySource from './AudioHistory.svelte?raw';

describe('BirdNET history listening-log layout', () => {
    it('keeps each history page short enough that supporting context remains reachable', () => {
        expect(audioHistorySource).toContain('const PAGE_SIZE = 25;');
    });

    it('puts the filterable detection record before secondary analytics', () => {
        const log = audioHistorySource.indexOf('data-audio-history-log');
        const analytics = audioHistorySource.indexOf('data-audio-history-analytics');

        expect(log).toBeGreaterThan(-1);
        expect(analytics).toBeGreaterThan(log);
    });

    it('uses one semantic table that reflows for phones without horizontal scrolling', () => {
        expect(audioHistorySource).toContain('data-audio-history-table');
        expect(audioHistorySource).toContain('md:table-row');
        expect(audioHistorySource).toContain('md:table-cell');
        expect(audioHistorySource).toContain('scope="col"');
        expect(audioHistorySource).not.toContain('overflow-x-auto');
    });

    it('removes the card wall, tiny labels, and emoji fallbacks', () => {
        expect(audioHistorySource.match(/card-base/g) ?? []).toHaveLength(0);
        expect(audioHistorySource).not.toMatch(/text-\[(?:9|10|11)px\]/);
        expect(audioHistorySource).not.toMatch(/[🐦🥇🥈🥉]/u);
    });

    it('uses restrained icons and accessible interaction states', () => {
        expect(audioHistorySource.match(/data-audio-section-icon/g) ?? []).toHaveLength(2);
        expect(audioHistorySource.match(/data-audio-section-icon[^>]+aria-hidden="true"/g) ?? []).toHaveLength(2);
        expect(audioHistorySource).toContain('min-h-11');
        expect(audioHistorySource).toContain('focus-visible:ring-2 focus-visible:ring-brand-500');
        expect(audioHistorySource).toContain('role="alert"');
        expect(audioHistorySource).toContain("$_('common.retry')");
        expect(audioHistorySource).toContain('animations: { enabled: !reduceMotion');
    });

    it('keeps the spectrogram as the meaningful per-detection artifact', () => {
        expect(audioHistorySource).toContain('data-audio-spectrogram');
        expect(audioHistorySource).toContain('loading="lazy"');
        expect(audioHistorySource).toContain('alt={detection.species}');
    });

    it('opens the existing species detail modal from each top-species row', () => {
        expect(audioHistorySource).toContain("import SpeciesDetailModal from '../components/SpeciesDetailModal.svelte'");
        expect(audioHistorySource).toContain('data-audio-top-species-button');
        expect(audioHistorySource).toContain('onclick={() => selectedSpecies = item.species}');
        expect(audioHistorySource).toContain("$_('leaderboard.view_species'");
        expect(audioHistorySource).toContain('<SpeciesDetailModal');
        expect(audioHistorySource).toContain('onclose={() => selectedSpecies = null}');
    });

    it('links automatic visual matches to their exact detection', () => {
        expect(audioHistorySource).toContain("import { appApiPath, toAppPath } from '../app/url-base'");
        expect(audioHistorySource).toContain('detection.matched_visual_event_id');
        expect(audioHistorySource).toContain('data-audio-visual-match-link');
        expect(audioHistorySource).toContain("toAppPath(`/events?event=${encodeURIComponent(detection.matched_visual_event_id)}`)");
        expect(audioHistorySource).toContain("$_('audio.table.open_visual_match')");
        expect(audioHistorySource).toContain('min-h-11 min-w-11');
    });
});
