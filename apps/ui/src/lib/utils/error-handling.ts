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
