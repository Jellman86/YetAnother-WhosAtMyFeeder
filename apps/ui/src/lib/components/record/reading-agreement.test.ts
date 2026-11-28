import { describe, expect, it } from 'vitest';
import type { Detection } from '../../api';
import { getBirdNames } from '../../naming';
import { readingDisagreement, readingNamingInput } from './reading-agreement';

const snapshot = { label: 'Columba palumbus', scientific_name: 'Columba palumbus', common_name: 'Common Wood-Pigeon', score: 0.99 };
const video = { label: 'Pica pica', scientific_name: 'Pica pica', common_name: 'Eurasian Magpie', score: 0.67 };
const disagreeing = {
    frigate_event: 'pigeon-magpie',
    display_name: 'Common Wood-Pigeon',
    category_name: 'Columba palumbus',
    score: 0.99,
    manual_tagged: false,
    video_classification_status: 'completed',
    video_classification_label: 'Pica pica',
    video_classification_score: 0.67,
    reading_agreement: 'disagree',
    snapshot_reading: snapshot,
    video_reading: video
} as Detection;

describe('readingDisagreement', () => {
    it('gives both named readings and asks for a person when the readings disagree', () => {
        expect(readingDisagreement(disagreeing)).toEqual({ snapshot, video, needsPerson: true });
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

    it('says nothing while a new video reading is under way or without both readings', () => {
        expect(readingDisagreement({ ...disagreeing, video_classification_status: 'processing' })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, snapshot_reading: null })).toBeNull();
        expect(readingDisagreement({ ...disagreeing, video_reading: null })).toBeNull();
    });
});

describe('readingNamingInput', () => {
    it('names both readings the same way, by the reader’s common name', () => {
        expect(getBirdNames(readingNamingInput(snapshot), true, false).primary).toBe('Common Wood-Pigeon');
        expect(getBirdNames(readingNamingInput(video), true, false).primary).toBe('Eurasian Magpie');
    });

    it('follows the scientific-name preference for both', () => {
        expect(getBirdNames(readingNamingInput(video), true, true).primary).toBe('Pica pica');
        expect(getBirdNames(readingNamingInput(snapshot), false, false).primary).toBe('Columba palumbus');
    });

    it('falls back to the stored label when the catalogue could not name the reading', () => {
        const unnamed = { label: 'Garden blackbird', scientific_name: null, common_name: null, score: 0.5 };
        expect(getBirdNames(readingNamingInput(unnamed), true, false).primary).toBe('Garden blackbird');
    });
});
