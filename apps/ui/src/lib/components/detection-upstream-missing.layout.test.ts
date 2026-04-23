import { describe, expect, it } from 'vitest';
import detectionCardSource from './DetectionCard.svelte?raw';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('upstream missing detection UI', () => {
    it('surfaces missing Frigate state on detection cards', () => {
        expect(detectionCardSource).toContain("detection.frigate_status === 'missing'");
        expect(detectionCardSource).toContain("$_('detection.upstream_missing.card_label'");
        expect(detectionCardSource).toContain("$_('detection.upstream_missing.card_title'");
    });

    it('surfaces missing Frigate details in the detection modal', () => {
        expect(detectionModalSource).toContain("detection.frigate_status === 'missing'");
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.title'");
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.description'");
        expect(detectionModalSource).toContain("$_('detection.upstream_missing.last_checked'");
    });
});
