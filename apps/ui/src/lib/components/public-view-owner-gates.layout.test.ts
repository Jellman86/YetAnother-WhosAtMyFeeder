import { describe, expect, it } from 'vitest';
import deskContextCardsSource from './DeskContextCards.svelte?raw';
import instancePipelineSource from './InstancePipeline.svelte?raw';

/**
 * A guest session must never fire requests that the backend will refuse with 403.
 * Camera status is an owner reading; the public surfaces either skip it or say
 * plainly that the reading belongs to the owner.
 */
describe('Public view owner-reading gates', () => {
    it('the dashboard desk only asks for camera status with owner access', () => {
        expect(deskContextCardsSource).toContain('authStore.hasOwnerAccess');
        expect(deskContextCardsSource).toContain('fetchCameraStatuses');
    });

    it('the about pipeline only asks for camera status with owner access', () => {
        expect(instancePipelineSource).toContain('authStore.hasOwnerAccess');
        expect(instancePipelineSource).toContain('fetchCameraStatuses');
    });

    it('the about pipeline tells guests a reading is owner-only instead of implying a fault', () => {
        expect(instancePipelineSource).toContain('about.pipeline.owner_only');
        expect(instancePipelineSource).toContain('about.pipeline.owner_only_detail');
    });
});
