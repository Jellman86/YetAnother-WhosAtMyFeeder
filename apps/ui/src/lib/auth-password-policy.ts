export const AUTH_PASSWORD_MIN_LENGTH_MESSAGE = 'Password must be at least 8 characters long';
export const AUTH_PASSWORD_COMPLEXITY_MESSAGE = 'Password must contain at least one letter and one number';

export function validateAuthPasswordPolicy(password: string): string | null {
    if (!password) {
        return null;
    }

    if (password.length < 8) {
        return AUTH_PASSWORD_MIN_LENGTH_MESSAGE;
    }

    if (!/[A-Za-z]/.test(password) || !/\d/.test(password)) {
        return AUTH_PASSWORD_COMPLEXITY_MESSAGE;
    }

    return null;
}
