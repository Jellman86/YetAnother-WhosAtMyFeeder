import { describe, expect, it } from 'vitest';
import detectionPreviewSource from './DetectionPreview.svelte?raw';
import { FIELD_LOG_GRID } from '../utils/field-log';

/**
 * The species name is the primary reading of a field log row. Thumbnails are a
 * recognition aid and must not grow until the name truncates at common desktop
 * widths, so the visible stack stays at two frames and the rest are counted.
 */
describe('Field log gives the species name priority over the thumbnail stack', () => {
    it('caps the visible thumbnail stack at two frames', () => {
        expect(detectionPreviewSource).toContain('const VISIBLE_FRAMES = 2;');
    });

    it('counts the frames the stack does not show', () => {
        expect(detectionPreviewSource).toContain('+{frameCount - VISIBLE_FRAMES}');
    });

    it('keeps the name column flexible in the row grid at every width', () => {
        // Phone, wide and narrow templates each give the name the flexible track.
        expect(FIELD_LOG_GRID.match(/minmax\(0,1fr\)/g)).toHaveLength(3);
    });
});
