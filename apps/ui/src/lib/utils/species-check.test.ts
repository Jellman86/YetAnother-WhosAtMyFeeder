import { describe, expect, it } from 'vitest';
import type { SearchResult, SnapshotCandidate } from '../api';
import { bestCrop, isBirdLineage, otherReads, regulars, suggestAnswer } from './species-check';

function candidate(id: string, mode: string, label: string | null, extra: Partial<SnapshotCandidate> = {}): SnapshotCandidate {
    return {
        candidate_id: id, source_mode: mode, classifier_label: label, classifier_score: 0.2, clip_variant: 'event', frame_index: 0,
        ranking_score: 0.5, selected: false, thumbnail_url: `/t/${id}.jpg`, image_url: `/i/${id}.jpg`, ...extra
    } as SnapshotCandidate;
}

const species = (common: string, scientific: string): SearchResult => ({ id: scientific, display_name: common, common_name: common, scientific_name: scientific });
const dunnock = species('Dunnock', 'Prunella modularis');
const robin = species('European Robin', 'Erithacus rubecula');
const greatTit = species('Great Tit', 'Parus major');

describe('the check sheet decisions', () => {
    it('shows a crop around the bird, never the whole scene', () => {
        const picked = bestCrop([
            candidate('scene', 'full_frame', null, { ranking_score: 0.9 }),
            candidate('hint', 'frigate_hint_crop', 'Prunella modularis', { ranking_score: 0.3 }),
            candidate('model', 'model_crop', 'Molothrus ater', { ranking_score: 0.6 })
        ]);
        expect(picked?.candidate_id).toBe('model');
    });

    it('prefers the crop the owner chose as the photograph', () => {
        expect(bestCrop([candidate('a', 'model_crop', null, { ranking_score: 0.9 }), candidate('b', 'model_crop', null, { selected: true })])?.candidate_id).toBe('b');
    });

    it('has no crop to show when only the scene was kept', () => {
        expect(bestCrop([candidate('scene', 'full_frame', null), candidate('kept', 'retained_photo', null)])).toBeNull();
    });

    it('reads the other names the crops were given, not the one the visit carries', () => {
        expect(otherReads([
            candidate('a', 'frigate_hint_crop', 'Prunella modularis'),
            candidate('b', 'model_crop', 'Molothrus ater'),
            candidate('c', 'full_frame', 'Periparus ater')
        ], 'Molothrus ater')).toEqual(['prunella modularis']);
    });

    it('suggests the feeder species most visits were also read as', () => {
        const suggestion = suggestAnswer({
            readsPerVisit: [['prunella modularis'], ['prunella modularis', 'parus major'], []],
            feeder: [robin, greatTit, dunnock],
            isBird: true,
            bestScore: 0.73
        });
        expect(suggestion).toEqual({ kind: 'rename', target: dunnock, reason: 'other_reads', visits: 2 });
    });

    it('ignores a read the feeder has never seen and falls back to its most common bird', () => {
        const suggestion = suggestAnswer({ readsPerVisit: [['mesembryanthemum cordifolium']], feeder: [dunnock, robin], isBird: true, bestScore: 0.66 });
        expect(suggestion).toEqual({ kind: 'rename', target: dunnock, reason: 'most_common' });
    });

    it('trusts a confident camera on something birders never report', () => {
        expect(suggestAnswer({ readsPerVisit: [[]], feeder: [dunnock], isBird: false, bestScore: 0.93 })).toEqual({ kind: 'confirm', reason: 'not_a_bird_confident' });
    });

    it('suggests hiding an unsure non-bird', () => {
        expect(suggestAnswer({ readsPerVisit: [[]], feeder: [dunnock], isBird: false, bestScore: 0.66 })).toEqual({ kind: 'hide', reason: 'not_a_bird_unsure' });
    });

    it('treats an unknown catalogue answer as a bird, so nothing is hidden on a guess', () => {
        expect(suggestAnswer({ readsPerVisit: [[]], feeder: [dunnock], isBird: null, bestScore: 0.95 })?.kind).toBe('rename');
    });

    it('knows a bird by class Aves and calls anything else not one', () => {
        expect(isBirdLineage([{ rank: 'class', scientific_name: 'Aves' }, { rank: 'species', scientific_name: 'Molothrus ater' }])).toBe(true);
        expect(isBirdLineage([{ rank: 'species', scientific_name: 'Aspidoscelis velox' }])).toBe(false);
        expect(isBirdLineage(null)).toBeNull();
    });

    it('lists the regulars without repeating the suggestion', () => {
        const suggestion = suggestAnswer({ readsPerVisit: [], feeder: [dunnock, robin, greatTit], isBird: true, bestScore: 0.7 });
        expect(regulars([dunnock, robin, greatTit], suggestion).map((entry) => entry.id)).toEqual([robin.id, greatTit.id]);
    });
});
