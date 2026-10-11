import { describe, expect, it, vi } from 'vitest';

vi.mock('../api', () => ({
    fetchEvents: vi.fn(),
    fetchEventsCount: vi.fn()
}));

const { DetectionsStore } = await import('./detections.svelte');

describe('DetectionsStore settled reclassifications', () => {
    it('versions a finished run once and ignores progress ticks and repeated completions', () => {
        const store = new DetectionsStore();
        store.startReclassification('A', 4, 'video');
        store.updateReclassificationProgress('A', 1, 4, 0.5, 'Robin');
        expect(store.settledMediaVersion('A')).toBe(0);

        store.completeReclassification('A', [], 'success');
        store.completeReclassification('A', [], 'success');

        expect(store.settledMediaVersion('A')).toBe(1);
        expect(store.settledMediaVersion('B')).toBe(0);
    });

    it('versions a run that finishes after its overlay was dismissed or never opened', () => {
        const store = new DetectionsStore();
        store.startReclassification('A', 4, 'video');
        store.dismissReclassification('A');

        store.completeReclassification('A', [], 'no_result');
        store.completeReclassification('Q', [], 'success');

        expect(store.settledMediaVersion('A')).toBe(1);
        expect(store.settledMediaVersion('Q')).toBe(2);
        expect(store.getReclassificationProgress('A')).toBeUndefined();
    });

    it('gives a new run after an earlier completed one a new version', () => {
        const store = new DetectionsStore();
        store.startReclassification('A', 4, 'video');
        store.completeReclassification('A', [], 'success');
        store.startReclassification('A', 4, 'video');
        store.completeReclassification('A', [], 'failed', 'video_timeout');

        expect(store.settledMediaVersion('A')).toBe(2);
    });

    it('settles and closes a hard failure, but not a dismissal by the owner', () => {
        const store = new DetectionsStore();
        store.startReclassification('A', 4, 'video');
        store.dismissReclassification('A');
        expect(store.settledMediaVersion('A')).toBe(0);

        store.startReclassification('A', 4, 'video');
        store.failReclassification('A');

        expect(store.settledMediaVersion('A')).toBe(1);
        expect(store.getReclassificationProgress('A')).toBeUndefined();
    });

    it('never reuses a version after an access change forgets which runs settled', () => {
        const store = new DetectionsStore();
        store.completeReclassification('A', [], 'success');
        const beforeReset = store.settledMediaVersion('A');

        store.resetForAccessChange();
        expect(store.settledMediaVersion('A')).toBe(0);

        store.completeReclassification('A', [], 'success');
        expect(store.settledMediaVersion('A')).toBeGreaterThan(beforeReset);
    });
});
