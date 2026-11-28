import { beforeAll, describe, expect, it } from 'vitest';
import { render } from 'svelte/server';
import { addMessages, init } from 'svelte-i18n';
import RecordReadings from './RecordReadings.svelte';
import modalSource from '../DetectionModal.svelte?raw';
import enDetection from '../../i18n/locales/en/detection.json';
import type { ReadingDisagreement } from './reading-agreement';

const disagreement: ReadingDisagreement = {
    snapshot: { display_name: 'Carrion Crow', category_name: 'Corvus corone', scientific_name: 'Corvus corone', common_name: 'Carrion Crow', score: 0.98 },
    videoLabel: 'Pica pica',
    videoScore: 0.68,
    needsPerson: true
};

function body(props: Partial<Parameters<typeof render<typeof RecordReadings>>[1]['props']> = {}): string {
    return render(RecordReadings, {
        props: { disagreement, snapshotName: 'Carrion Crow', videoName: 'Pica pica', videoInput: 'Cropped video frames', ...props }
    }).body;
}

function text(html: string): string {
    return html.replace(/<!--[^>]*-->/g, '').replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

beforeAll(() => {
    addMessages('en', { detection: enDetection });
    init({ fallbackLocale: 'en', initialLocale: 'en' });
});

describe('the snapshot and video readings on a record', () => {
    it('shows both readings with their scores and says in words that a person is needed', () => {
        const html = body();
        expect(html).toContain('data-record-readings="needs-person"');
        expect(html).toContain('data-status-chip="attention"');
        const words = text(html);
        expect(words).toContain('Readings disagree');
        expect(words).toContain('The snapshot and the video named different birds.');
        expect(words).toMatch(/Snapshot Carrion Crow 98%/);
        expect(words).toMatch(/Video Pica pica 68% Cropped video frames/);
    });

    it('keeps the readings as evidence without amber once the owner has named the bird', () => {
        const html = body({ disagreement: { ...disagreement, needsPerson: false } });
        expect(html).toContain('data-record-readings="decided"');
        expect(html).not.toContain('data-status-chip');
        expect(text(html)).toContain('You chose the name shown.');
    });

    it('offers to score the clip again only when given the action', () => {
        expect(body()).not.toContain('data-record-readings-score-again');
        expect(body({ onscoreagain: () => {} })).toContain('data-record-readings-score-again');
    });

    it('replaces the held-back notice and the video card in the record rather than repeating them', () => {
        expect(modalSource).toContain('videoPromotionGated && hasOwnerDetectionActions && onReclassify && !readings');
        expect(modalSource).toMatch(/\{#if readings\}\s*<RecordReadings[\s\S]*?\{:else if detection\.video_classification_status === 'completed'/);
    });
});
