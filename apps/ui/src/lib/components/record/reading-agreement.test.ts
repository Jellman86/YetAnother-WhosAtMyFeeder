import { describe, expect, it } from 'vitest';
import type { Detection } from '../../api';
import { readingDisagreement } from './reading-agreement';

const snapshot = { display_name: 'Carrion Crow', category_name: 'Corvus corone', scientific_name: 'Corvus corone', common_name: 'Carrion Crow', score: 0.98 };
const disagreeing = {
    frigate_event: 'crow-magpie',
    display_name: 'Carrion Crow',
    category_name: 'Corvus corone',
    score: 0.98,
    manual_tagged: false,
    video_classification_status: 'completed',
    video_classification_label: 'Pica pica',
    video_classification_score: 0.68,
    reading_agreement: 'disagree',
    snapshot_reading: snapshot
} as Detection;

describe('readingDisagreement', () => {
    it('shows both readings and asks for a person when the readings disagree', () => {
        expect(readingDisagreement(disagreeing)).toEqual({
            snapshot,
            videoLabel: 'Pica pica',
            videoScore: 0.68,
            needsPerson: true
        });
    });

    it('keeps both readings but asks nobody once the owner has named the bird', () => {
        expect(readingDisagreement({ ...disagreeing, manual_tagged: true })?.needsPerson).toBe(false);
    });

    it('says nothing when the readings agree, could not be compared or were never compared', () => {
        expect(readingDisagreement({ ...disagreeing, reading_agreement: 'agree' })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, reading_agreement: 'cannot_compare' })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, reading_agreement: null })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, reading_agreement: undefined })).toBeNull();
    });

    it('says nothing while a new video reading is under way or without the snapshot it compared with', () => {
        expect(readingDisagreement({ ...disagreeing, video_classification_status: 'processing' })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, snapshot_reading: null })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, video_classification_label: undefined })).toBeNull();
    });
});
