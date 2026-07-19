export const AUTH_PASSWORD_MIN_LENGTH_MESSAGE = 'Password must be at least 8 characters long';
export const AUTH_PASSWORD_COMPLEXITY_MESSAGE = 'Password must contain at least one letter and one number';
export const AUTH_PASSWORD_MAX_BYTES = 72;
export const AUTH_PASSWORD_MAX_BYTES_MESSAGE = 'Password must use 72 UTF-8 bytes or fewer';
export const AUTH_PASSWORD_REQUIREMENTS_MESSAGE = `${AUTH_PASSWORD_COMPLEXITY_MESSAGE}. ${AUTH_PASSWORD_MAX_BYTES_MESSAGE}.`;
export const AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE = 'Password is required when enabling authentication';
export const AUTH_PASSWORD_MISMATCH_MESSAGE = 'Passwords do not match';

type AuthSettingsSaveValidationInput = {
    authEnabled: boolean;
    authHasPassword: boolean;
    authPassword: string;
    authPasswordConfirm: string;
};

export function validateAuthPasswordPolicy(password: string): string | null {
    if (!password) {
        return null;
    }

    if (password.length < 8) {
        return AUTH_PASSWORD_MIN_LENGTH_MESSAGE;
    }

    if (new TextEncoder().encode(password).byteLength > AUTH_PASSWORD_MAX_BYTES) {
        return AUTH_PASSWORD_MAX_BYTES_MESSAGE;
    }

    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        return AUTH_PASSWORD_COMPLEXITY_MESSAGE;
    }

    return null;
}

export function validateAuthSettingsSave({
    authEnabled,
    authHasPassword,
    authPassword,
    authPasswordConfirm
}: AuthSettingsSaveValidationInput): string | null {
    if (authPassword || authPasswordConfirm) {
        if (authPassword !== authPasswordConfirm) {
            return AUTH_PASSWORD_MISMATCH_MESSAGE;
        }

        return validateAuthPasswordPolicy(authPassword);
    }

    if (authEnabled && !authHasPassword) {
        return AUTH_PASSWORD_REQUIRED_TO_ENABLE_MESSAGE;
    }

    return null;
}
