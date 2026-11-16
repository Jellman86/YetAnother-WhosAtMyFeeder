import { describe, expect, it } from 'vitest';
import { conflictValueText } from './conflict-values';

const translate = (key: string, options?: { default?: string }): string => options?.default ?? key;

describe('conflictValueText', () => {
    it('words a switch as on or off', () => {
        expect(conflictValueText(true, translate)).toBe('On');
        expect(conflictValueText(false, translate)).toBe('Off');
    });

    it('shows numbers and text as they are', () => {
        expect(conflictValueText(0.72, translate)).toBe('0.72');
        expect(conflictValueText('birdtable', translate)).toBe('birdtable');
    });

    it('says a cleared value is not set rather than showing an empty quote', () => {
        expect(conflictValueText(null, translate)).toBe('Not set');
        expect(conflictValueText('', translate)).toBe('Not set');
        expect(conflictValueText([], translate)).toBe('Not set');
    });

    it('lists the entries of a list', () => {
        expect(conflictValueText(['cat', 'fox'], translate)).toBe('cat, fox');
    });

    it('cuts a long value so the save bar stays one line per setting', () => {
        const text = conflictValueText('x'.repeat(80), translate);
        expect(text.length).toBeLessThanOrEqual(41);
        expect(text.endsWith('…')).toBe(true);
    });

    it('does not print the structure of a value it cannot word', () => {
        expect(conflictValueText({ nested: { a: 1 } }, translate)).toBe('A different value');
    });
});
