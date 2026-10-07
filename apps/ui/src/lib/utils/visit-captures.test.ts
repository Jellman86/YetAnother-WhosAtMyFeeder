import { describe, expect, it } from 'vitest';
import type { Detection } from '../api';
import type { DetectionVisit } from '../api/visits';
import { captureFacts, hasCaptureFooter, hasCaptureTimeline } from './visit-captures';

type Summary = NonNullable<Detection['bird_summary']>;

function summary(counted: number, overrides: Partial<Summary> = {}): Summary {
    return { counted, unknown: 0, excluded: 0, species: [], hint_only: false, ...overrides };
}

function capture(event: string, overrides: Partial<Detection> = {}): Detection {
    return {
        frigate_event: event,
        display_name: 'Turdus merula',
        score: 0.9,
        detection_time: '2026-10-02T10:42:21Z',
        camera_name: 'birdcam',
        ...overrides
    };
}

function visit(captureCount: number, representative = capture('shown')): DetectionVisit {
    return {
        visit_id: representative.frigate_event,
        start_time: representative.detection_time,
        end_time: representative.detection_time,
        capture_count: captureCount,
        best_score: representative.score,
        needs_review: false,
        audio_confirmed: false,
        representative,
        latest: representative,
        peak_capture: null
    };
}

describe('hasCaptureTimeline', () => {
    it('offers no capture list for a single capture, which the row already is', () => {
        expect(hasCaptureTimeline(visit(1))).toBe(false);
    });

    it('offers the chronological captures once a visit holds more than one', () => {
        expect(hasCaptureTimeline(visit(2))).toBe(true);
    });
});

describe('hasCaptureFooter', () => {
    it('gives a single uncounted capture no footer, so its card keeps the plain shape', () => {
        expect(hasCaptureFooter(visit(1))).toBe(false);
    });

    it('gives a visit of several captures a footer for its list', () => {
        expect(hasCaptureFooter(visit(2))).toBe(true);
    });

    it('gives a single capture a footer only to state several birds in it', () => {
        const busy = { ...visit(1), peak_capture: capture('shown', { bird_summary: summary(2) }) };
        const lone = { ...visit(1), peak_capture: capture('shown', { bird_summary: summary(1) }) };
        expect(hasCaptureFooter(busy)).toBe(true);
        expect(hasCaptureFooter(lone)).toBe(false);
    });
});

describe('captureFacts', () => {
    it('marks the capture the visit uses as its photograph', () => {
        expect(captureFacts(capture('shown'), visit(3)).shown).toBe(true);
        expect(captureFacts(capture('other'), visit(3)).shown).toBe(false);
    });

    it('states the birds in one capture only when the count says more than a bird', () => {
        expect(captureFacts(capture('a', { bird_summary: summary(3) }), visit(3)).birds).toBe(3);
        expect(captureFacts(capture('a', { bird_summary: summary(1) }), visit(3)).birds).toBeNull();
    });

    it('says nothing about birds for a capture that was never counted, because not counted is not zero', () => {
        expect(captureFacts(capture('a'), visit(3)).birds).toBeNull();
        expect(captureFacts(capture('a', { bird_summary: null }), visit(3)).birds).toBeNull();
        expect(captureFacts(capture('a', { bird_summary: summary(0, { excluded: 2 }) }), visit(3)).birds).toBeNull();
    });

    it('reports a matching call only for camera captures', () => {
        expect(captureFacts(capture('a', { audio_confirmed: true }), visit(3)).heard).toBe(true);
        expect(captureFacts(capture('a', { audio_confirmed: false }), visit(3)).heard).toBe(false);
        expect(
            captureFacts(capture('a', { audio_confirmed: true, observation_source: 'manual_upload' }), visit(3)).heard
        ).toBe(false);
    });
});

describe('captureFacts favourites', () => {
    it('marks each favourite capture, so several favourites in one visit can be told apart (#481)', () => {
        expect(captureFacts(capture('a', { is_favorite: true }), visit(3)).favorite).toBe(true);
        expect(captureFacts(capture('a', { is_favorite: false }), visit(3)).favorite).toBe(false);
        expect(captureFacts(capture('a'), visit(3)).favorite).toBe(false);
    });
});
