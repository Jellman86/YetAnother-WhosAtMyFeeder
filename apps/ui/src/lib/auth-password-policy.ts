const AUTH_PASSWORD_MIN_LENGTH = 8;
const AUTH_PASSWORD_MAX_BYTES = 72;

/** What is wrong with a password, named so the caller can word it in the reader's language. */
export type PasswordProblem = 'too_short' | 'too_long' | 'needs_letter_and_number' | 'mismatch' | 'required';

export interface PolicyMessage {
    key: string;
    default: string;
}

/** The rules shown beside a new-password field. */
export const AUTH_PASSWORD_REQUIREMENTS: PolicyMessage = {
    key: 'auth.password_policy.requirements',
    default: 'At least 8 characters, with at least one letter and one number. No more than 72 bytes: accented and non-Latin letters take more than one.'
};

const PROBLEM_DEFAULTS: Record<PasswordProblem, string> = {
    too_short: 'The password must be at least 8 characters long.',
    too_long: 'The password must use 72 bytes or fewer. Accented and non-Latin letters take more than one byte.',
    needs_letter_and_number: 'The password must contain at least one letter and one number.',
    mismatch: 'The passwords do not match.',
    required: 'Enter a password to turn on authentication.'
};

export function passwordProblemMessage(problem: PasswordProblem): PolicyMessage {
    return { key: `auth.password_policy.${problem}`, default: PROBLEM_DEFAULTS[problem] };
}

type AuthSettingsSaveValidationInput = {
    authEnabled: boolean;
    authHasPassword: boolean;
    authPassword: string;
    authPasswordConfirm: string;
};

export function validateAuthPasswordPolicy(password: string): PasswordProblem | null {
    if (!password) {
        return null;
    }

    if (password.length < AUTH_PASSWORD_MIN_LENGTH) {
        return 'too_short';
    }

    // bcrypt reads only the first 72 bytes, so the server refuses anything longer.
    if (new TextEncoder().encode(password).byteLength > AUTH_PASSWORD_MAX_BYTES) {
        return 'too_long';
    }

    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        return 'needs_letter_and_number';
    }

    return null;
}

export function validateAuthSettingsSave({
    authEnabled,
    authHasPassword,
    authPassword,
    authPasswordConfirm
}: AuthSettingsSaveValidationInput): PasswordProblem | null {
    if (authPassword || authPasswordConfirm) {
        if (authPassword !== authPasswordConfirm) {
            return 'mismatch';
        }

        return validateAuthPasswordPolicy(authPassword);
    }

    if (authEnabled && !authHasPassword) {
        return 'required';
    }

    return null;
}
