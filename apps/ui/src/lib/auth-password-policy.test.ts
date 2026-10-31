import { describe, expect, it } from 'vitest';

import en from './i18n/locales/en.json';
import {
    AUTH_PASSWORD_REQUIREMENTS,
    passwordProblemMessage,
    validateAuthSettingsSave,
    validateAuthPasswordPolicy,
    type PasswordProblem
} from './auth-password-policy';

describe('validateAuthPasswordPolicy', () => {
    it('accepts empty input so unchanged settings passwords can pass through', () => {
        expect(validateAuthPasswordPolicy('')).toBeNull();
    });

    it('rejects passwords shorter than eight characters', () => {
        expect(validateAuthPasswordPolicy('abc123')).toBe('too_short');
    });

    it('rejects passwords without a numeric character', () => {
        expect(validateAuthPasswordPolicy('abcdefgh')).toBe('needs_letter_and_number');
    });

    it('rejects passwords without an alphabetic character', () => {
        expect(validateAuthPasswordPolicy('12345678')).toBe('needs_letter_and_number');
    });

    it('accepts passwords with both letters and numbers', () => {
        expect(validateAuthPasswordPolicy('abc12345')).toBeNull();
    });

    it('accepts passwords that are exactly 72 UTF-8 bytes', () => {
        expect(validateAuthPasswordPolicy(`A1${'é'.repeat(35)}`)).toBeNull();
    });

    it('rejects passwords longer than 72 UTF-8 bytes', () => {
        expect(validateAuthPasswordPolicy(`A1${'é'.repeat(36)}`)).toBe('too_long');
    });

    it('requires a password when enabling auth on a passwordless instance', () => {
        expect(
            validateAuthSettingsSave({
                authEnabled: true,
                authHasPassword: false,
                authPassword: '',
                authPasswordConfirm: '',
            })
        ).toBe('required');
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
        ).toBe('mismatch');
    });
});

describe('password policy wording', () => {
    const problems: PasswordProblem[] = ['too_short', 'too_long', 'needs_letter_and_number', 'mismatch', 'required'];

    it('words every problem through a locale key whose English default matches the locale', () => {
        const policy = en.auth.password_policy as Record<string, string>;
        for (const problem of problems) {
            const message = passwordProblemMessage(problem);
            expect(message.key).toBe(`auth.password_policy.${problem}`);
            expect(message.default).toBe(policy[problem]);
        }
        expect(AUTH_PASSWORD_REQUIREMENTS.key).toBe('auth.password_policy.requirements');
        expect(AUTH_PASSWORD_REQUIREMENTS.default).toBe(policy.requirements);
    });
});
