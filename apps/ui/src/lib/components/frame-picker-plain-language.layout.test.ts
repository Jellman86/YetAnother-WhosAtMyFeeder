import { describe, expect, it } from 'vitest';
import stripSource from './FrameStrip.svelte?raw';
import modalSource from './DetectionModal.svelte?raw';

describe('the frame strip names pictures, not subsystems (#256)', () => {
    // "Frigate hint crop" and "Model crop" describe which part of the app produced a frame.
    // Somebody choosing the most representative photograph does not care, and making them
    // care is a cost with no return. The strip shows moments; the pop-out says how a moment
    // is framed, and Details keeps the provenance.

    it('describes framing, not provenance, in the pop-out', () => {
        expect(stripSource).toContain('detection.snapshot_framing_whole');
        expect(stripSource).toContain('detection.snapshot_framing_close');
        expect(stripSource).toContain('detection.snapshot_framing_as_recorded');
    });

    it('has retired the subsystem vocabulary from the record', () => {
        for (const source of [stripSource, modalSource]) {
            expect(source).not.toContain('snapshot_source_frigate_hint_crop');
            expect(source).not.toContain('snapshot_source_model_crop');
            expect(source).not.toContain('snapshot_source_unknown');
            expect(source).not.toContain('snapshot_picker_sources');
        }
    });

    it('still reports the species a moment was read as, labelled as a read', () => {
        expect(stripSource).toContain('moment.read');
        expect(stripSource).toContain('detection.frame_model_read');
    });
});
