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
    return connectionCauseMessage(cause, service, address);
}

/**
 * The sentence for a connection that failed with a known cause code, or null for a code or service
 * this page has no words for. Health uses it for the broker session's last failure, so the reader
 * sees the cause and what to check, not the resolver's errno text.
 */
export function connectionCauseMessage(cause: string, service: string, address: string): string | null {
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

const DELIVERY_CHANNELS: Record<string, string> = { discord: 'Discord', pushover: 'Pushover', telegram: 'Telegram' };
const DELIVERY_CAUSES: Record<string, string> = {
    not_configured_discord: '{channel} is not set up yet. Enter the webhook address, then test again.',
    not_configured_pushover: '{channel} is not set up yet. Enter the user key and API token, then test again.',
    not_configured_telegram: '{channel} is not set up yet. Enter the bot token and chat ID, then test again.',
    no_answer_address: '{channel} did not answer. Check the webhook address, then test again.',
    no_answer_network: '{channel} did not answer. Check that YA-WAMF can reach the internet, then test again.',
    timeout: '{channel} took too long to answer. Wait a moment, then test again.',
    refused_discord: '{channel} refused the message. Check the webhook address, then test again.',
    refused_pushover: '{channel} refused the message. Check the user key and API token, then test again.',
    refused_telegram: '{channel} refused the message. Check the bot token and chat ID, then test again.',
    unexpected_reply: 'Something answered in place of {channel}. Check for a proxy or sign-in page between YA-WAMF and the internet, then test again.',
    rate_limited: '{channel} is limiting messages for now. Wait a minute, then test again.',
    provider_error: '{channel} reported a problem on its side. Wait a few minutes, then test again.'
};

/** The sentence a cause has on a channel: what to check depends on which credentials the channel takes. */
function deliverySentenceKey(cause: string, channel: string): string {
    if (cause === 'refused' || cause === 'not_configured') return `${cause}_${channel}`;
    // Only Discord's address is the owner's to get wrong; the others have one fixed address.
    if (cause === 'no_answer') return channel === 'discord' ? 'no_answer_address' : 'no_answer_network';
    return cause;
}

/**
 * A channel test that was not delivered answers with a cause code and the channel. The sentence
 * and its next step are written here from the code, so they read in the page's language.
 */
function deliveryFailureMessage(payload: object): string | null {
    const { cause, channel } = payload as { cause?: unknown; channel?: unknown };
    if (typeof cause !== 'string' || typeof channel !== 'string' || !Object.hasOwn(DELIVERY_CHANNELS, channel)) return null;
    const key = deliverySentenceKey(cause, channel);
    if (!Object.hasOwn(DELIVERY_CAUSES, key)) return null;
    return worded(`errors.delivery.${key}`, DELIVERY_CAUSES[key], { channel: DELIVERY_CHANNELS[channel] });
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

    const deliveryFailure = deliveryFailureMessage(payload);
    if (deliveryFailure) return deliveryFailure;

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

/** Cancels a response body nothing will read; one already read or being read is left alone. */
export function discardBody(response: Response): void {
    if (response.body && !response.bodyUsed && !response.body.locked) {
        void response.body.cancel().catch(() => undefined);
    }
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
    // Neither was written for a person, so the body is never shown, and it is cancelled rather
    // than left unread: a stalled one would hold the connection open past the caller's deadline.
    discardBody(response);
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
