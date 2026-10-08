import { describe, expect, it } from 'vitest';
import source from './DetectionModal.svelte?raw';

/**
 * An uploaded video is kept with the observation, and photo choices and Score again read it
 * like any visit's clip (#481). The record used to hide all three for every upload, so they
 * never appeared even after the server could serve them. An uploaded photo has no frames.
 */
describe('an uploaded video gets the same photo and scoring controls as a visit', () => {
    it('gates them on having frames to work from, not on being an upload', () => {
        expect(source).toContain("const hasFrameSource = $derived(!isManualObservation || Boolean(detection.has_clip));");
        expect(source).not.toContain("detection.observation_source !== 'manual_upload'");
    });

    it('offers the frame picker, the counted birds and Score again whenever there are frames', () => {
        expect(source).toMatch(/const showInlineFramePicker = \$derived\(\s*hasOwnerDetectionActions\s*&& hasFrameSource/);
        expect(source).toContain('{#if hasOwnerDetectionActions && hasFrameSource}');
        expect(source).toMatch(/\{#if hasFrameSource\}\s*<button\s*type="button"\s*onclick=\{handleReclassifyClick\}/);
    });
});
