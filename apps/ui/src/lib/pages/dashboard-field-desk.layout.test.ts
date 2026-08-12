import { describe, expect, it } from 'vitest';

import dashboardSource from './Dashboard.svelte?raw';
import fieldLogSource from '../components/FieldLog.svelte?raw';
import histogramSource from '../components/DailyHistogram.svelte?raw';
import previewSource from '../components/DetectionPreview.svelte?raw';
import recentAudioSource from '../components/RecentAudio.svelte?raw';
import reviewQueueSource from '../components/ReviewQueueCard.svelte?raw';
import visitorsSource from '../components/TopVisitors.svelte?raw';

describe('dashboard field desk layout', () => {
    it('leads with the chronological log and docks the outstanding work beside it', () => {
        const fieldDesk = dashboardSource.indexOf('data-dashboard-field-desk');
        const fieldLog = dashboardSource.indexOf('<FieldLog');
        const reviewQueue = dashboardSource.indexOf('<ReviewQueueCard');
        const topVisitors = dashboardSource.indexOf('data-dashboard-top-visitors');

        expect(fieldDesk).toBeGreaterThan(-1);
        expect(fieldLog).toBeGreaterThan(fieldDesk);
        expect(reviewQueue).toBeGreaterThan(fieldLog);
        expect(topVisitors).toBeGreaterThan(reviewQueue);
    });

    it('keeps top visitors at full width instead of compressing it into the rail', () => {
        const aside = dashboardSource.indexOf('<aside');
        const asideEnd = dashboardSource.indexOf('</aside>');
        const topVisitors = dashboardSource.indexOf('data-dashboard-top-visitors');

        expect(topVisitors).toBeGreaterThan(-1);
        // The component lays out horizontally; an 18rem rail breaks it.
        expect(topVisitors > aside && topVisitors < asideEnd).toBe(false);
    });

    it('keeps the review queue and its actions to owners', () => {
        // Identify and hide are owner-only calls, so a guest must not be offered them.
        expect(dashboardSource).toContain('let canReview = $derived(authStore.hasOwnerAccess)');
        expect(dashboardSource).toContain('{#if canReview}');
        expect(dashboardSource).toContain('{#if reviewSessionOpen && canReview}');
        expect(dashboardSource).toContain('canIdentify={canReview}');
        expect(fieldLogSource).toContain('{#if visit.needsReview && canIdentify}');
    });

    it('folds repeat frames into visits instead of printing one card per frame', () => {
        expect(dashboardSource).toContain('groupDetectionsIntoVisits(deskDetections)');
        expect(dashboardSource).toContain('buildReviewQueue(deskDetections)');
        expect(dashboardSource).not.toContain('LatestDetectionHero');
        expect(dashboardSource).not.toContain('data-dashboard-discovery-feed');
    });

    it('describes one window everywhere so the desk cannot contradict itself', () => {
        expect(dashboardSource).toContain('withinDeskWindow(detectionsStore.detections)');
        expect(dashboardSource).toContain('detections={deskDetections}');
        // The overview ribbon is replaced by the compact day bar.
        expect(dashboardSource).not.toContain('StatsRibbon');
        expect(dashboardSource).toContain('<DayBar');
    });

    it('keeps every visit row reachable and shows why a row is flagged', () => {
        expect(fieldLogSource).toContain('data-field-log-row');
        expect(fieldLogSource).toContain('data-needs-review');
        // Colour alone must not carry the flag (CLAUDE.md §5).
        expect(fieldLogSource).toContain('dashboard.field_log.needs_name');
        expect(fieldLogSource).toContain('dashboard.field_log.identify');
        expect(fieldLogSource).toContain('min-h-11');
    });

    it('draws the day as one thread and says when it is only showing part of it', () => {
        // The spine runs behind the nodes; without it the rows read as unrelated cards.
        expect(fieldLogSource).toContain('The spine runs behind the nodes');
        expect(fieldLogSource).toContain('data-field-log-more');
        expect(fieldLogSource).toContain('dashboard.field_log.earlier');
        expect(dashboardSource).toContain('hiddenCount={hiddenVisitCount}');
    });

    it('states both empty and loading states rather than rendering nothing', () => {
        expect(fieldLogSource).toContain('data-field-log-loading');
        expect(fieldLogSource).toContain('dashboard.waiting_first_visitor');
        expect(reviewQueueSource).toContain('dashboard.review_queue.empty');
    });

    it('opens the capture preview on hover and on keyboard focus, and dismisses it', () => {
        expect(previewSource).toContain('onmouseenter={show}');
        expect(previewSource).toContain('onfocusin={show}');
        expect(previewSource).toContain('onfocusout={handleFocusOut}');
        expect(previewSource).toContain("event.key === 'Escape'");
        // The pointer must be able to travel into the panel (WCAG 2.2 SC 1.4.13).
        expect(previewSource).toContain('CLOSE_GRACE_MS');
        expect(previewSource).toContain('motion-reduce:animate-none');
        expect(previewSource).toContain('aria-expanded={open}');
        expect(previewSource).toContain('focus-ring');
    });

    it('reuses the existing thumbnail proxy for the preview instead of a second endpoint', () => {
        expect(previewSource).toContain("import { getThumbnailUrl } from '../api'");
        expect(previewSource).toContain('loading="lazy"');
        expect(previewSource.match(/getThumbnailUrl/g) ?? []).toHaveLength(3);
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
        expect(visitorsSource).not.toContain('data-top-visitors-ranking-icon');
        expect(visitorsSource).toContain('data-dashboard-species-portrait');
        expect(visitorsSource).toContain('<ol');
        expect(visitorsSource).toContain('rounded-full');
        expect(visitorsSource).not.toContain('card-base');
    });

    it('finishes the audio preview without a doubled bottom rule', () => {
        expect(recentAudioSource).toContain('data-audio-history-action');
        expect(recentAudioSource).toContain('data-dashboard-audio-list');
        expect(recentAudioSource).toMatch(/data-dashboard-audio[^>]+border-t/);
        expect(recentAudioSource).not.toMatch(/data-dashboard-audio[^>]+border-y/);
        expect(recentAudioSource).not.toMatch(/data-dashboard-audio-list[^>]+border-y/);
    });
});
