type ValidationDetail = {
    loc?: Array<string | number>;
    msg?: string;
};

function normalizeMessage(value: string): string {
    return value.replace(/^Value error,\s*/i, '').trim();
}

function getFieldLabel(loc: Array<string | number> | undefined): string | null {
    if (!Array.isArray(loc)) {
        return null;
    }

    const filtered = loc
        .filter((part) => typeof part === 'string')
        .map((part) => part.trim())
        .filter((part) => part && part !== 'body' && part !== 'query' && part !== 'path');

    return filtered.length > 0 ? filtered[filtered.length - 1] : null;
}

function formatValidationDetails(details: ValidationDetail[]): string | null {
    const formatted = details
        .map((detail) => {
            const message = typeof detail?.msg === 'string' ? normalizeMessage(detail.msg) : '';
            if (!message) {
                return null;
            }

            const field = getFieldLabel(detail.loc);
            return field ? `${field}: ${message}` : message;
        })
        .filter((value): value is string => Boolean(value));

    if (formatted.length === 0) {
        return null;
    }

    if (formatted.length === 1) {
        const [only] = formatted;
        const colonIndex = only.indexOf(': ');
        return colonIndex >= 0 ? only.slice(colonIndex + 2) : only;
    }

    return formatted.join('; ');
}

export function extractApiErrorMessage(payload: unknown, fallback: string): string {
    if (typeof payload === 'string') {
        const text = payload.trim();
        return text || fallback;
    }

    if (!payload || typeof payload !== 'object') {
        return fallback;
    }

    const detail = (payload as { detail?: unknown }).detail;
    if (typeof detail === 'string') {
        const text = detail.trim();
        return text || fallback;
    }

    if (Array.isArray(detail)) {
        return formatValidationDetails(detail as ValidationDetail[]) || fallback;
    }

    if (detail && typeof detail === 'object') {
        const nestedMessage = (detail as { msg?: unknown; message?: unknown }).msg
            ?? (detail as { message?: unknown }).message;
        if (typeof nestedMessage === 'string' && nestedMessage.trim()) {
            return normalizeMessage(nestedMessage);
        }
    }

    const message = (payload as { message?: unknown }).message;
    if (typeof message === 'string' && message.trim()) {
        return normalizeMessage(message);
    }

    return fallback;
}

export async function readApiErrorMessage(response: Response, fallback: string): Promise<string> {
    const contentType = response.headers.get('content-type') || '';

    if (contentType.includes('application/json')) {
        const payload = await response.json().catch(() => null);
        return extractApiErrorMessage(payload, fallback);
    }

    const text = await response.text().catch(() => '');
    return extractApiErrorMessage(text, fallback);
}
