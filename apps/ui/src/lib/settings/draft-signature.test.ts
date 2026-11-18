import { describe, expect, it } from 'vitest';
import { draftSignature } from './draft-signature';

describe('a signature of unsaved values', () => {
    it('is the same for the same values and differs for different ones, without holding the text', () => {
        const typed = JSON.stringify([['mqtt_password', 'hunter2']]);
        expect(draftSignature(typed)).toBe(draftSignature(typed));
        expect(draftSignature(typed)).not.toBe(draftSignature(JSON.stringify([['mqtt_password', 'hunter3']])));
        expect(draftSignature(typed)).toMatch(/^[0-9a-f]{8}$/);
        expect(draftSignature(typed)).not.toContain('hunter');
    });
});
