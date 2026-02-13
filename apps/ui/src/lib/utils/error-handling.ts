/**
 * Utility functions for safe error handling
 */

/**
 * Safely extract error message from unknown error type
 */
export function getErrorMessage(error: unknown): string {
    if (error instanceof Error) {
        return error.message;
    }
    if (typeof error === 'string') {
        return error;
    }
    if (error && typeof error === 'object' && 'message' in error) {
        return String(error.message);
    }
    return 'An unknown error occurred';
}

/**
 * Detect network/request failures that are often transient in browser sessions.
 */
export function isTransientRequestError(error: unknown): boolean {
    if (error instanceof DOMException && error.name === 'AbortError') {
        return true;
    }
    if (error instanceof Error && error.name === 'AbortError') {
        return true;
    }

    const message = getErrorMessage(error).toLowerCase();
    return (
        message.includes('failed to fetch') ||
        message.includes('networkerror') ||
        message.includes('load failed') ||
        message.includes('the operation was aborted') ||
        message.includes('aborterror')
    );
}

/**
 * Type guard to check if value is an Error
 */
export function isError(error: unknown): error is Error {
    return error instanceof Error;
}

/**
 * Safely log error with context
 */
export function logError(context: string, error: unknown): void {
    const message = getErrorMessage(error);
    console.error(`[${context}]`, message, error);
}

/**
 * Format error for user display (hide sensitive details)
 */
export function formatUserError(error: unknown): string {
    const message = getErrorMessage(error);
    // Remove stack traces and sensitive paths
    return message.split('\n')[0];
}
