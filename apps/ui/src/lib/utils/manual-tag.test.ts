import { describe, expect, it } from 'vitest';
import type { Detection, UpdateDetectionResult } from '../api';
import { applyManualTagResult } from './manual-tag';

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
