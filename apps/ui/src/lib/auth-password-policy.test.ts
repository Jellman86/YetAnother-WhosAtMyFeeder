import { describe, expect, it } from 'vitest';

import {
    AUTH_PASSWORD_COMPLEXITY_MESSAGE,
    validateAuthPasswordPolicy
} from './auth-password-policy';

describe('validateAuthPasswordPolicy', () => {
    it('accepts empty input so unchanged settings passwords can pass through', () => {
        expect(validateAuthPasswordPolicy('')).toBeNull();
    });

    it('rejects passwords shorter than eight characters', () => {
        expect(validateAuthPasswordPolicy('abc123')).toBe('Password must be at least 8 characters long');
    });

    it('rejects passwords without a numeric character', () => {
        expect(validateAuthPasswordPolicy('abcdefgh')).toBe(AUTH_PASSWORD_COMPLEXITY_MESSAGE);
    });

    it('rejects passwords without an alphabetic character', () => {
        expect(validateAuthPasswordPolicy('12345678')).toBe(AUTH_PASSWORD_COMPLEXITY_MESSAGE);
    });

    it('accepts passwords with both letters and numbers', () => {
        expect(validateAuthPasswordPolicy('abc12345')).toBeNull();
    });
});
