import { describe, expect, it } from 'vitest';
import eventsSource from './Events.svelte?raw';
import detectionsStoreSource from '../stores/detections.svelte.ts?raw';

describe('event request lifecycle', () => {
    it('gives page and shared-store requests separate cancellation ownership', () => {
        expect(eventsSource).toContain("requestKey: 'events-page:list'");
        expect(eventsSource).toContain("requestKey: 'events-page:count'");
        expect(detectionsStoreSource).toContain("requestKey: 'detections-store:list'");
        expect(detectionsStoreSource).toContain("requestKey: 'detections-store:count'");
    });

    it('does not let a superseded response overwrite the current events page', () => {
        expect(eventsSource).toContain('const loadGeneration = ++eventsLoadGeneration;');
        expect(eventsSource).toContain('if (loadGeneration !== eventsLoadGeneration) return;');
        expect(eventsSource).toContain('if (loadGeneration === eventsLoadGeneration) loading = false;');
    });
});
