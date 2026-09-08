export interface StreamTicket {
    ticket: string;
    expires_in_seconds: number;
}

export type StreamTicketMinter = () => Promise<StreamTicket>;

/**
 * Build the URL the live stream opens with.
 *
 * `EventSource` cannot send headers, so a signed-in session has to put *something*
 * in the query string — and nginx logs the full request line to its error log
 * whenever the upstream is down, which it is for a few seconds on every container
 * start. So the session token never goes in the URL. A single-use ticket does: it
 * is spent on first use and expires in a minute, so a logged copy is worthless.
 *
 * A fresh ticket is minted on every call because each one opens the stream exactly
 * once; the reconnect path must call this again rather than reuse a URL. A failed
 * exchange is thrown, not swallowed: opening the stream as a guest with a session
 * still present would silently drop owner-only events.
 */
export async function resolveStreamUrl(
    base: string,
    hasSession: boolean,
    mintTicket: StreamTicketMinter
): Promise<string> {
    if (!hasSession) return base;
    const { ticket } = await mintTicket();
    const separator = base.includes('?') ? '&' : '?';
    return `${base}${separator}ticket=${encodeURIComponent(ticket)}`;
}
