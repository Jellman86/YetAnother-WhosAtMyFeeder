import { describe, expect, it } from 'vitest';

import dashboardSource from './Dashboard.svelte?raw';
import histogramSource from '../components/DailyHistogram.svelte?raw';
import heroSource from '../components/LatestDetectionHero.svelte?raw';
import recentAudioSource from '../components/RecentAudio.svelte?raw';
import statsSource from '../components/StatsRibbon.svelte?raw';
import visitorsSource from '../components/TopVisitors.svelte?raw';

describe('dashboard live observation desk layout', () => {
    it('keeps the latest visitor as the primary anchor before supporting activity', () => {
        const observationDesk = dashboardSource.indexOf('data-dashboard-observation-desk');
        const topVisitors = dashboardSource.indexOf('data-dashboard-top-visitors');
        const discoveryFeed = dashboardSource.indexOf('data-dashboard-discovery-feed');

        expect(observationDesk).toBeGreaterThan(-1);
        expect(topVisitors).toBeGreaterThan(observationDesk);
        expect(discoveryFeed).toBeGreaterThan(topVisitors);
    });

    it('uses one divided overview surface instead of four metric cards', () => {
        expect(statsSource).toContain('data-dashboard-overview');
        expect(statsSource).toContain('<dl');
        expect(statsSource).toContain('divide-x');
        expect(statsSource.match(/card-base/g) ?? []).toHaveLength(0);
        expect(statsSource).toContain('data-dashboard-top-visitor-portrait');
        expect(statsSource).toContain('rounded-full');
    });

    it('presents activity and audio as quiet operational sections', () => {
        expect(histogramSource).toContain('data-dashboard-activity');
        expect(histogramSource).toContain('role="img"');
        expect(histogramSource).not.toContain('card-base');
        expect(recentAudioSource).toContain('data-dashboard-audio');
        expect(recentAudioSource).toContain('divide-y');
        expect(recentAudioSource).not.toContain('card-base');
    });

    it('uses compact round species portraits for visitor recognition', () => {
        expect(visitorsSource).toContain('fetchSpeciesInfo');
        expect(visitorsSource).toContain('data-top-visitors-ranking-icon');
        expect(visitorsSource).toContain('data-dashboard-species-portrait');
        expect(visitorsSource).toContain('<ol');
        expect(visitorsSource).toContain('rounded-full');
        expect(visitorsSource).not.toContain('card-base');
        expect(heroSource).toContain('data-dashboard-hero-species-portrait');
        expect(heroSource).toContain('rounded-full');
    });

    it('finishes the audio preview without a doubled bottom rule', () => {
        expect(recentAudioSource).toContain('data-audio-history-action');
        expect(recentAudioSource).toContain('data-dashboard-audio-list');
        expect(recentAudioSource).toMatch(/data-dashboard-audio[^>]+border-t/);
        expect(recentAudioSource).not.toMatch(/data-dashboard-audio[^>]+border-y/);
        expect(recentAudioSource).not.toMatch(/data-dashboard-audio-list[^>]+border-y/);
    });
});
