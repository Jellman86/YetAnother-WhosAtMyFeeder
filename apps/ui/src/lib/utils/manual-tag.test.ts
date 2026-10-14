import { describe, expect, it } from 'vitest';
import type { Detection, UpdateDetectionResult } from '../api';
import { applyManualTagResult } from './manual-tag';
import { buildReviewQueue } from './review-queue';

const detection = {
    frigate_event: 'event-1',
    display_name: 'Blue Tit',
    category_name: 'Cyanistes caeruleus',
    scientific_name: 'Cyanistes caeruleus',
    common_name: 'Blue Tit',
    taxa_id: 144028,
    manual_tagged: false,
    camera_name: 'front',
    detection_time: '2026-08-12T08:00:00Z',
    score: 0.52,
    ai_analysis: 'The bird stayed briefly at the feeder.',
    ai_analysis_timestamp: '2026-08-12T08:05:00Z'
} as Detection;

describe('applyManualTagResult', () => {
    for (const status of ['unchanged', 'updated'] as const) {
        it(`clears a whole-view review after a saved ${status} owner choice without a page refresh`, () => {
            const initial = { source: 'recording_frame', is_cropped: false };
            const wholeView = { ...detection, score: 0.98, classification_input: initial, initial_classification_input: initial };
            expect(buildReviewQueue([wholeView], { reviewThreshold: 0.6 }).total).toBe(1);
            const updated = applyManualTagResult(wholeView, {
                status, event_id: detection.frigate_event, new_species: detection.display_name,
                manual_tagged: true
            });
            expect(updated.classification_input).toEqual({ source: 'owner_species_choice' });
            expect(updated.initial_classification_input).toEqual(initial);
            expect(buildReviewQueue([updated], { reviewThreshold: 0.6 }).total).toBe(0);
        });
    }

    it('keeps model evidence when the response does not record an owner decision', () => {
        const wholeView = { ...detection, classification_input: { source: 'recording_frame', is_cropped: false } };
        const updated = applyManualTagResult(wholeView, {
            status: 'unchanged', event_id: detection.frigate_event, new_species: detection.display_name,
            manual_tagged: false
        });
        expect(updated.classification_input).toEqual(wholeView.classification_input);
    });

    it('removes a same-species confirmation from the local queue without waiting for SSE', () => {
        const result = {
            status: 'unchanged',
            event_id: 'event-1',
            new_species: 'Blue Tit',
            species: 'Blue Tit',
            old_species: 'Blue Tit',
            category_name: 'Cyanistes caeruleus',
            scientific_name: 'Cyanistes caeruleus',
            common_name: 'Blue Tit',
            taxa_id: 144028,
            manual_tagged: true
        } satisfies UpdateDetectionResult;

        expect(applyManualTagResult(detection, result)).toMatchObject({
            display_name: 'Blue Tit',
            category_name: 'Cyanistes caeruleus',
            manual_tagged: true,
            ai_analysis: 'The bird stayed briefly at the feeder.',
            ai_analysis_timestamp: '2026-08-12T08:05:00Z'
        });
    });

    it('applies the canonical names returned by the server after a correction', () => {
        const result = {
            status: 'updated',
            event_id: 'event-1',
            new_species: 'Great Tit',
            old_species: 'Blue Tit',
            category_name: 'Parus major',
            scientific_name: 'Parus major',
            common_name: 'Great Tit',
            taxa_id: 145252,
            manual_tagged: true
        } satisfies UpdateDetectionResult;

        expect(applyManualTagResult(detection, result)).toMatchObject({
            display_name: 'Great Tit',
            category_name: 'Parus major',
            scientific_name: 'Parus major',
            common_name: 'Great Tit',
            taxa_id: 145252,
            manual_tagged: true,
            ai_analysis: null,
            ai_analysis_timestamp: null
        });
    });
});
