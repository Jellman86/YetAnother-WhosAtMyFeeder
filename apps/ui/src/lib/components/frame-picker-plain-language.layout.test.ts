import { describe, expect, it } from 'vitest';
import modalSource from './DetectionModal.svelte?raw';

describe('the frame picker names pictures, not subsystems (#256)', () => {
    // "Frigate hint crop" and "Model crop" describe which part of the app
    // produced a frame. Somebody choosing the most representative photograph
    // does not care, and making them care is a cost with no return. What does
    // help is how the picture is framed: the whole scene, or close on the bird.

    it('offers framing, not provenance', () => {
        expect(modalSource).toContain('detection.snapshot_framing_whole');
        expect(modalSource).toContain('detection.snapshot_framing_close');
    });

    it('has retired the subsystem vocabulary from the picker', () => {
        expect(modalSource).not.toContain('snapshot_source_frigate_hint_crop');
        expect(modalSource).not.toContain('snapshot_source_model_crop');
        expect(modalSource).not.toContain('snapshot_source_unknown');
    });

    it('still prefers the species a frame was read as, when it has one', () => {
        expect(modalSource).toContain('candidate.classifier_label ??');
    });
});
