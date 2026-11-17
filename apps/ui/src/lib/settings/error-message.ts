/**
 * The words of a failed request: its own message, or the `detail` or `message` of a JSON error
 * body carried in it, else the fallback.
 */
export function requestErrorMessage(error: unknown, fallback: string): string {
    const message = error instanceof Error ? error.message : fallback;
    if (typeof message === 'string' && message.trim().startsWith('{')) {
        try {
            const parsed: unknown = JSON.parse(message);
            const payload = parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
            return String(payload.detail || payload.message || fallback);
        } catch {
            return message;
        }
    }
    return message;
}
