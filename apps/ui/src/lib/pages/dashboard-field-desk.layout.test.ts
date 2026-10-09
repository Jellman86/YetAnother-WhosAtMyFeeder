import { describe, expect, it } from 'vitest';

import dashboardSource from './Dashboard.svelte?raw';
import fieldLogSource from '../components/FieldLog.svelte?raw';
import visitRowSource from '../components/FieldLogVisitRow.svelte?raw';
import notableNearbySource from '../components/NotableNearby.svelte?raw';
import histogramSource from '../components/DailyHistogram.svelte?raw';
import previewSource from '../components/DetectionPreview.svelte?raw';
import recentAudioSource from '../components/RecentAudio.svelte?raw';
import reviewQueueSource from '../components/ReviewQueueCard.svelte?raw';
import visitorsSource from '../components/TopVisitors.svelte?raw';
import visitGroupingSource from '../utils/visit-grouping.ts?raw';

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

    it('places location-level notable reports beneath the field log, not in a detection', () => {
        expect(dashboardSource).toContain('data-dashboard-field-log-column');
        expect(dashboardSource).toContain('<NotableNearby');
        expect(notableNearbySource).toContain('data-dashboard-notable-nearby');
        expect(notableNearbySource).toContain('fetchEbirdNotable({ distKm, daysBack })');
        expect(notableNearbySource).toContain('dashboard.notable_nearby.scope');
    });

    it('handles a disabled notable datasource without making an eBird request', () => {
        expect(notableNearbySource).toContain('if (!sourceEnabled)');
        expect(notableNearbySource).toContain('dashboard.notable_nearby.unavailable');
        expect(notableNearbySource).toContain('{#if canConfigure}');
        expect(notableNearbySource).toContain('dashboard.notable_nearby.configure');
        expect(notableNearbySource).toContain('role="alert"');
        expect(notableNearbySource).toContain('dashboard.notable_nearby.retry');
    });

    it('orders the rail from what is happening to what is merely interesting', () => {
        const aside = dashboardSource.indexOf('<aside');
        const asideEnd = dashboardSource.indexOf('</aside>');
        const order = ['<ReviewQueueCard', '<DeskContextCards', '<RecentAudio', '<DailyHistogram', 'data-dashboard-top-visitors'].map(
            (marker) => dashboardSource.indexOf(marker)
        );
        for (const at of order) expect(at > aside && at < asideEnd).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
        // A compact vertical list now, so it belongs in the rail rather than a near-empty band.
        expect(visitorsSource).toContain('<ol class="divide-y');
        expect(visitorsSource).not.toContain('xl:grid-cols-5');
    });

    it('counts visits everywhere the desk says visits', () => {
        // The summary's frame count is a different unit; the day bar takes its visit count.
        expect(dashboardSource).toContain('let last24hCount = $derived(summary?.visit_count ?? allVisits.length);');
        expect(dashboardSource).toContain('<DailyHistogram data={summary.hourly_visits ?? []} currentHour={summaryHour} />');
        expect(dashboardSource).toContain('cameraVisits={summary?.camera_visits ?? null}');
        expect(visitorsSource).toContain('item.visit_count ?? item.count');
        expect(histogramSource).toContain("dashboard.histogram.visits_per_hour");
    });

    it('draws the rolling day so it ends now, and says when it was busiest', () => {
        expect(histogramSource).toContain('const hour = (currentHour + 1 + offset) % 24;');
        expect(histogramSource).toContain('data-dashboard-activity-peak');
        expect(histogramSource).toContain("dashboard.histogram.now");
        // No unlabelled total competing with the day bar.
        expect(histogramSource).not.toContain('text-2xl font-bold tabular-nums text-brand-700');
    });

    it('keeps the review queue and its actions to owners', () => {
        // Identify and hide are owner-only calls, so a guest must not be offered them.
        expect(dashboardSource).toContain('let canReview = $derived(authStore.hasOwnerAccess)');
        expect(dashboardSource).toContain('{#if canReview}');
        expect(dashboardSource).toContain('{#if reviewSessionOpen && canReview}');
        expect(dashboardSource).toContain('canIdentify={canReview}');
        expect(visitRowSource).toContain('{#if visit.needsReview && canIdentify}');
    });

    it('folds repeat frames into visits instead of printing one card per frame', () => {
        expect(dashboardSource).toContain("fetchVisits({ ...window, limit: VISIT_ROW_LIMIT, signal, requestKey: 'dashboard:visits' })");
        expect(dashboardSource).toContain('buildReviewQueue(deskDetections, { reviewThreshold, newSpecies: newSpeciesEntries })');
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

    it('says in words when a visit was confirmed by a matching call', () => {
        // The header counts cross-confirmed visits; a row confirmed by a heard call says so beside
        // its name at every width, and each capture that was heard says so in the visit's list, with
        // the same words the record uses.
        expect(visitRowSource).toContain('{#if visit.audioConfirmed}');
        expect(visitRowSource).toContain('data-field-log-audio');
        expect(visitRowSource.split("$_('detection.fact_heard_yes', { default: 'matching call' })").length).toBe(3);
        expect(visitGroupingSource).toContain('audioConfirmed: frames.some(');
    });

    it('keeps every visit row reachable and shows why a row is flagged', () => {
        expect(fieldLogSource).toContain('data-field-log-row');
        expect(visitRowSource).toContain('data-needs-review');
        // Colour alone must not carry the flag (CLAUDE.md §5).
        expect(visitRowSource).toContain('dashboard.field_log.needs_name');
        expect(visitRowSource).toContain('dashboard.field_log.identify');
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
        // Every frame in a visit previews itself, so the handlers take the frame index.
        expect(previewSource).toContain("onpointerenter={(event) => { if (event.pointerType !== 'touch') show(index); }}");
        expect(previewSource).toContain('onfocusin={(event) => { if (isKeyboardFocus(event.target)) show(index); }}');
        expect(previewSource).toContain('let openIndex = $state<number | null>(null)');
        expect(previewSource).toContain('dashboard.field_log.preview_frame_position');
        expect(previewSource).toContain('onfocusout={handleFocusOut}');
        expect(previewSource).toContain("event.key === 'Escape'");
        // The pointer must be able to travel into the panel (WCAG 2.2 SC 1.4.13).
        expect(previewSource).toContain('CLOSE_GRACE_MS');
        expect(previewSource).toContain('motion-reduce:animate-none');
        // A tooltip trigger does not disclose a region it owns: the panel is
        // portalled to the body with no DOM or aria-controls linkage, so
        // aria-expanded announced a state that pointed at nothing.
        expect(previewSource).not.toContain('aria-expanded');
        expect(previewSource).toContain('focus-ring');
    });

    it('reuses the existing thumbnail proxy for the preview instead of a second endpoint', () => {
        expect(previewSource).toContain("import { getThumbnailUrl } from '../api'");
        expect(previewSource).toContain('loading="lazy"');
        // Stack and panel draw the same proxy address; thumbnail-refresh.spec.ts proves both
        // show it. No other media endpoint may creep in beside it.
        expect(previewSource).not.toMatch(/['"`]\/api\//);
        expect(previewSource).toContain('onopen?.(frame)');
        expect(visitRowSource).toContain('onopen={(frame) => onselect?.(frame)}');
        expect(previewSource).toContain('min-h-11 min-w-11');
    });


    it('presents activity and audio as quiet operational sections', () => {
        expect(histogramSource).toContain('data-dashboard-activity');
        expect(histogramSource).toContain('role="img"');
        expect(histogramSource).not.toContain('card-base');
        expect(recentAudioSource).toContain('data-dashboard-audio');
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

    it('frames every desk section as one panel with one header shape', () => {
        // Each rail section is a ruled panel that opens with the same display heading and a
        // muted window line, so the three columns read as one set rather than three styles.
        for (const source of [recentAudioSource, histogramSource, visitorsSource]) {
            expect(source).toContain('font-display text-xl font-bold text-slate-950 dark:text-white');
            expect(source).toMatch(/<section[^>]*class="panel /);
        }
        expect(fieldLogSource).toContain('<section class="panel space-y-4" data-dashboard-field-log>');
        expect(notableNearbySource).toContain('class="panel space-y-4"');
        expect(recentAudioSource).toContain('data-audio-history-action');
    });

    it('splits the rail into what needs you and the reference on a wide screen', () => {
        const now = dashboardSource.indexOf('data-dashboard-rail-now');
        const reference = dashboardSource.indexOf('data-dashboard-rail-reference');
        expect(now).toBeGreaterThan(dashboardSource.indexOf('<aside'));
        expect(reference).toBeGreaterThan(now);
        expect(dashboardSource.indexOf('<ReviewQueueCard')).toBeLessThan(reference);
        expect(dashboardSource.indexOf('<NotableNearby')).toBeGreaterThan(reference);
        expect(dashboardSource).toContain('3xl:grid-cols-2');
    });
});
