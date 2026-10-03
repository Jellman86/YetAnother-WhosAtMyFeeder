import { describe, expect, it } from 'vitest';
import countedBirdsSource from './CountedBirds.svelte?raw';
import detectionModalSource from './DetectionModal.svelte?raw';
import reviewQueueSource from './ReviewQueueModal.svelte?raw';
import fieldLogSource from './FieldLogVisitRow.svelte?raw';
import dashboardSource from '../pages/Dashboard.svelte?raw';

/**
 * Birds are counted on one whole frame and their boxes are that frame's pixels. These checks
 * hold the wiring that keeps outlines on the right scene and edits on the right bird.
 */
describe('Counted birds keep scene, bird and capture identity', () => {
    it('draws outlines only from the resolved full-resolution count scene', () => {
        expect(countedBirdsSource).toContain('resolveCountScene(birds, candidates)');
        expect(countedBirdsSource).toContain('sceneGeometryIsValid(birds, sceneSize)');
        expect(countedBirdsSource).not.toContain('thumbnail_url');
    });

    it('never turns a drawn box into a control', () => {
        expect(countedBirdsSource).toMatch(/pointer-events-none absolute rounded-sm[^"]*"[^>]*data-counted-bird-outline/s);
        expect(countedBirdsSource).not.toMatch(/<button[^>]*data-counted-bird-outline/);
    });

    it('keys rows and edits by stable observation id', () => {
        expect(countedBirdsSource).toContain('{#each shownRows as bird (bird.id)}');
        expect(countedBirdsSource).toContain('updateCountedBird(requestEvent, bird.id, change)');
        expect(countedBirdsSource).toContain('requestGeneration !== generation');
    });

    it('resets per-capture state by keying the component to the capture in both records', () => {
        expect(detectionModalSource).toContain('{#key detection.frigate_event}');
        expect(detectionModalSource).toContain('generation={countedBirdsGeneration}');
        expect(reviewQueueSource).toContain('{#key current.frigate_event}');
        expect(reviewQueueSource).toContain('generation={countedBirdsGeneration}');
    });

    it('advances the bird generation inside effects without subscribing to it', () => {
        for (const source of [detectionModalSource, reviewQueueSource]) {
            expect(source).toContain('untrack(() => { countedBirdsGeneration += 1; });');
            expect(source.match(/^ {8}countedBirdsGeneration \+= 1;$/gm) ?? []).toEqual([]);
        }
    });

    it('outlines the whole-scene peek only on the full-resolution image', () => {
        expect(detectionModalSource).toContain('if (!sceneUrl || !sceneImageEl || sceneImageEl.getAttribute(\'src\') !== sceneUrl) {');
        expect(reviewQueueSource).toContain('if (!fullFrame?.image_url || !sceneEl || sceneEl.getAttribute(\'src\') !== fullFrame.image_url) {');
    });

    it('refreshes the field log from the server after a bird edit instead of patching it', () => {
        expect(dashboardSource).toContain('void detectionsStore.refreshAfterOwnerEdit();');
        expect(fieldLogSource).toContain('visitBirdMarker(visit)');
        expect(fieldLogSource).not.toContain('updateDetection');
    });
});
