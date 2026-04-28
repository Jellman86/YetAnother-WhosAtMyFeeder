import { describe, expect, it } from 'vitest';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('DetectionModal video promotion gating', () => {
    it('uses the shared identity-aware gated-promotion helper', () => {
        expect(detectionModalSource).toContain("from '../video-promotion-gate'");
        expect(detectionModalSource).toContain('isVideoPromotionGated(detection)');
    });
});
