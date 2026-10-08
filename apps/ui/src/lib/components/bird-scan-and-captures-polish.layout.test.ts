import { describe, expect, it } from 'vitest';
import scan from './BirdScanControl.svelte?raw';
import fieldLog from './FieldLogVisitRow.svelte?raw';

/**
 * On a phone the bird scan read as a bordered card around a freehand two-bird glyph that looked
 * like a chain link, and the field log's capture count was a white bordered pill in front of its
 * chevron, louder than the name beside it.
 */
describe('the bird scan row', () => {
    it('is one recessed row, status first and the action after it', () => {
        expect(scan).toContain('<div class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl bg-slate-100');
        expect(scan).not.toContain('rounded-lg border border-slate-200 bg-white p-3');
        expect(scan.indexOf('role="status"')).toBeLessThan(scan.indexOf('class="btn btn-secondary'));
    });

    it('uses a viewfinder icon rather than the freehand birds', () => {
        expect(scan).toContain('M4 8V6a2 2 0 0 1 2-2h2M16 4h2a2 2 0 0 1 2 2v2');
        expect(scan).not.toContain('M3 16c1-4 3-6 6-5');
    });
});

describe('the field log capture count on a phone', () => {
    it('is a borderless tinted chip with the chevron after the count', () => {
        const chip = fieldLog.slice(fieldLog.indexOf('data-field-log-captures-phone'), fieldLog.indexOf('data-field-log-captures-phone') + 1500);
        expect(chip).not.toContain('border border-slate-300');
        expect(chip.indexOf('{capturesText}')).toBeLessThan(chip.indexOf('<svg'));
        expect(chip).toContain('bg-slate-100 text-slate-600');
    });
});
