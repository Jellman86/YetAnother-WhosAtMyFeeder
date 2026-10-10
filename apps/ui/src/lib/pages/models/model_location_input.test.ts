import { describe, expect, it } from 'vitest';

import { usesSavedFeederLocation } from './model_location_input';

describe('usesSavedFeederLocation', () => {
    it('is true when the model declares the iNat 2021 location contract', () => {
        expect(usesSavedFeederLocation({ preprocessing: { metadata_input: 'inat2021_location_v1' } })).toBe(true);
    });

    it('is false for models without a metadata contract', () => {
        expect(usesSavedFeederLocation({ preprocessing: null })).toBe(false);
        expect(usesSavedFeederLocation({ preprocessing: undefined })).toBe(false);
        expect(usesSavedFeederLocation({})).toBe(false);
        expect(usesSavedFeederLocation({ preprocessing: { resize: 384 } })).toBe(false);
    });

    it('is false for an unknown or malformed contract, so guidance never overclaims', () => {
        expect(usesSavedFeederLocation({ preprocessing: { metadata_input: 'inat2021_location_v2' } })).toBe(false);
        expect(usesSavedFeederLocation({ preprocessing: { metadata_input: true } })).toBe(false);
        expect(usesSavedFeederLocation({ preprocessing: { metadata_input: ' inat2021_location_v1 ' } })).toBe(false);
    });
});
