import { describe, expect, it } from 'vitest';
import modalSource from './ReviewQueueModal.svelte?raw';
import dashboardSource from '../pages/Dashboard.svelte?raw';

describe('review queue walk-through', () => {
    it('is its own flow rather than the detection modal', () => {
        expect(dashboardSource).toContain('<ReviewQueueModal');
        expect(dashboardSource).toContain('reviewSessionOpen = true');
        // Working the queue must not bounce the user to Explorer.
        expect(dashboardSource).not.toContain("onreviewall={() => onnavigate?.('/events')}");
    });

    it('behaves as a dialog: labelled, trapped, escapable', () => {
        expect(modalSource).toContain('role="dialog"');
        expect(modalSource).toContain('aria-modal="true"');
        expect(modalSource).toContain('aria-labelledby="review-session-title"');
        expect(modalSource).toContain('trapFocus(dialogEl)');
        expect(modalSource).toContain("event.key === 'Escape'");
        expect(modalSource).toContain('use:portal');
    });

    it('states position, progress and what is left', () => {
        expect(modalSource).toContain('dashboard.review_session.position');
        expect(modalSource).toContain('dashboard.review_session.remaining');
        expect(modalSource).toContain('motion-reduce:transition-none');
    });

    it('offers species this feeder sees before the full label list', () => {
        expect(modalSource).toContain('dashboard.review_session.seen_here');
        expect(modalSource).toContain('suggestions.slice(0, 8)');
        expect(dashboardSource).toContain('suggestions={recentSpecies}');
        // The alphabetical head of an 11,000-label list is invertebrates, not birds.
        expect(modalSource).not.toContain('labels.slice(0, 8)');
    });

    it('shows the crop the classifier scored when one exists, and says so when it does not', () => {
        expect(modalSource).toContain('fetchSnapshotCandidates');
        expect(modalSource).toContain('crop.image_url ?? crop.thumbnail_url');
        expect(modalSource).toContain('fullFrame.image_url ?? fullFrame.thumbnail_url');
        expect(modalSource).toContain("import { findMatchingFullFrameCandidate } from '../utils/detection-evidence'");
        expect(modalSource).toMatch(
            /findMatchingFullFrameCandidate\(\s*response\.candidates \?\? \[\],\s*preferredCrop\?\.candidate_id \?\? null\s*\)/
        );
        expect(modalSource).toContain('dashboard.review_session.crop');
        expect(modalSource).toContain('dashboard.review_session.full_frame');
        expect(modalSource).toContain('aria-pressed={view === \'crop\'}');
        expect(modalSource).toContain("{#if crop?.thumbnail_url && fullFrame?.thumbnail_url}");
        // Crops only exist for scanned events, so their absence is stated, not hidden.
        expect(modalSource).toContain('dashboard.review_session.no_crop');
    });

    it('offers a way out of every item, including one that is not a bird', () => {
        expect(modalSource).toContain('dashboard.review_session.skip');
        expect(modalSource).toContain('dashboard.review_session.not_a_bird');
        expect(modalSource).toContain('dashboard.review_session.full_record');
    });

    it('ends with an honest summary rather than silently closing', () => {
        expect(modalSource).toContain('dashboard.review_session.done');
        expect(modalSource).toContain('dashboard.review_session.skipped_note');
    });

    it('degrades when a snapshot is missing instead of showing a hole', () => {
        expect(modalSource).toContain('let failedImageUrls = $state<Set<string>>(new Set())');
        expect(modalSource).toContain('failedImageUrls.has(imageUrl)');
    });
});
