import { get } from 'svelte/store';
import { _ } from 'svelte-i18n';

/**
 * A sentence in the reader's language. The dictionary may not be loaded yet when a very early
 * request fails, so the English default stands in rather than the error being lost.
 */
function worded(key: string, fallback: string, values?: Record<string, string>): string {
    try {
        return get(_)(key, { default: fallback, values });
    } catch {
        return fallback.replace(/\{(\w+)\}/g, (_match, name: string) => values?.[name] ?? '');
    }
}

/** What a 5xx with no stated reason says: the cause as far as it is known, and the next step. */
function serverFailureMessage(): string {
    return worded(
        'errors.server_failure',
        'Something on the server stopped this request. Try again; if it keeps happening, open System health to see what is wrong.'
    );
}

/** A caller that passes only the status has no explanation of its own to give. */
function isBareStatus(fallback: string): boolean {
    return /^HTTP \d+$/.test(fallback);
}

const CONNECTION_CAUSES: Record<string, string> = {
    host_not_found: '{service}: the host name in {address} was not found. Check the address.',
    refused: '{service}: nothing answered at {address}. Check that it is running and that the port is right.',
    timeout: '{service}: no answer from {address} in time. Check the address and that this machine can reach it.',
    not_authorised: '{service}: the user name or password was refused. Check them, or turn authentication off if it accepts anonymous clients.',
    unreachable: '{service}: could not connect to {address}. Check the address and the port.'
};
/** How each service is named in the sentence. A product name is the same in every language. */
function connectionServiceName(service: string): string | null {
    if (service === 'mqtt') return worded('errors.connection.service_mqtt', 'MQTT broker');
    if (service === 'birdnet') return 'BirdNET-Go';
    return null;
}

/**
 * A failed connection test answers with a cause code, the service and a reduced address. The
 * sentence is written here from the code, so it reads in the page's language, not the server's.
 */
function connectionFailureMessage(payload: object): string | null {
    const { cause, service, address } = payload as { cause?: unknown; service?: unknown; address?: unknown };
    if (typeof cause !== 'string' || typeof service !== 'string' || typeof address !== 'string') return null;
    const serviceName = connectionServiceName(service);
    if (!Object.hasOwn(CONNECTION_CAUSES, cause) || serviceName === null) return null;
    // An address given as a URL has a scheme, and a wrong http or https is a common cause.
    if (cause === 'unreachable' && address.includes('://')) {
        return worded('errors.connection.unreachable_url', '{service}: could not connect to {address}. Check the address, scheme and port.', {
            service: serviceName,
            address
        });
    }
    return worded(`errors.connection.${cause}`, CONNECTION_CAUSES[cause], { service: serviceName, address });
}

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

    const connectionFailure = connectionFailureMessage(payload);
    if (connectionFailure) return connectionFailure;

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
    // Without a reason from the server, a caller's own explanation stands; one that passed only
    // the status gets the server-failure sentence for a 5xx, because "HTTP 500" explains nothing.
    const unexplained = response.status >= 500 && isBareStatus(fallback) ? serverFailureMessage() : fallback;

    if (contentType.includes('application/json')) {
        const payload = await response.json().catch(() => null);
        return extractApiErrorMessage(payload, unexplained);
    }

    // Anything else is a gateway page or a framework's bare status text ("Internal Server Error").
    // Neither was written for a person, so the body is never shown.
    return unexplained;
}

/**
 * Returns true when an error is a transient gateway/infrastructure error (HTTP 502/503/504)
 * that will self-heal on the next poll tick and is never user-actionable.
 */
export function isTransientGatewayError(error: unknown): boolean {
    if (!(error instanceof Error)) return false;
    // The status is the fact; the message is now a translated sentence and cannot be matched.
    const status = (error as { status?: unknown }).status;
    if (typeof status === 'number') return status === 502 || status === 503 || status === 504;
    return /^HTTP 50[234]/.test(error.message);
}
