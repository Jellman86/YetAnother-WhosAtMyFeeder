import { describe, expect, it } from 'vitest';

import {
    AUTH_PASSWORD_COMPLEXITY_MESSAGE,
    AUTH_PASSWORD_MAX_BYTES_MESSAGE,
    AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE,
    validateAuthSettingsSave,
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

    it('accepts passwords that are exactly 72 UTF-8 bytes', () => {
        expect(validateAuthPasswordPolicy(`A1${'é'.repeat(35)}`)).toBeNull();
    });

    it('rejects passwords longer than 72 UTF-8 bytes', () => {
        expect(validateAuthPasswordPolicy(`A1${'é'.repeat(36)}`)).toBe(AUTH_PASSWORD_MAX_BYTES_MESSAGE);
    });

    it('requires a password when enabling auth on a passwordless instance', () => {
        expect(
            validateAuthSettingsSave({
                authEnabled: true,
                authHasPassword: false,
                authPassword: '',
                authPasswordConfirm: '',
            })
        ).toBe(AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE);
    });

    it('allows enabling auth without entering a new password when one already exists', () => {
        expect(
            validateAuthSettingsSave({
                authEnabled: true,
                authHasPassword: true,
                authPassword: '',
                authPasswordConfirm: '',
            })
        ).toBeNull();
    });

    it('rejects mismatched confirmation in auth settings save', () => {
        expect(
            validateAuthSettingsSave({
                authEnabled: true,
                authHasPassword: false,
                authPassword: 'abc12345',
                authPasswordConfirm: 'abc12346',
            })
        ).toBe('Passwords do not match');
    });
});
