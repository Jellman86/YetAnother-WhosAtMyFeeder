import type { AudioSourceOption } from '../api/audio';

/**
 * A camera's audio link is a list of BirdNET-Go source names and stream ids, matched literally by
 * the server. BirdNET-Go keeps a stream's id when the stream is renamed, so Settings links by id
 * where the source sends one, and shows the stream's current name beside it.
 */

export interface LinkTokenDescription {
    /** The first line: the stream's current name for a linked id, otherwise the token as typed. */
    name: string;
    /** The line beneath a linked id: the id, unless the stream sent no name and the first line is the id. */
    id: string | null;
    /** The installs sending a linked id, when more than one does. */
    install: string | null;
    /** The newest visible call the token matches, as the API sent it; null when none does. */
    lastHeard: string | null;
}

export interface RenamedLink {
    token: string;
    source: AudioSourceOption;
}

/**
 * Close to how the server compares a link (`normalize_mapping_key`: trimmed and case-folded), but
 * not exact: upper then lower case also joins pairs Python's casefold keeps apart, such as "Pinar"
 * and "Pınar". It only decides which link a date or a notice belongs to, and whether a picked
 * source is linked already; it never removes or rewrites a link.
 */
function fold(value: string | null | undefined): string {
    return (value ?? '').trim().toUpperCase().toLowerCase();
}

export function sameLinkToken(a: string | null | undefined, b: string | null | undefined): boolean {
    return fold(a) === fold(b);
}

/** A typed link split the way the server reads it. */
export function linkTokens(mapping: string | null | undefined): string[] {
    return (mapping ?? '')
        .split(/[,\n;|]+/)
        .map((token) => token.trim())
        .filter(Boolean);
}

export function addLinkToken(tokens: string[], value: string): string[] {
    const next = value.trim();
    if (!next || tokens.some((token) => sameLinkToken(token, next))) return tokens;
    return [...tokens, next];
}

function streamsWithId(id: string, sources: AudioSourceOption[]): AudioSourceOption[] {
    return sources.filter((source) => source.source_id && sameLinkToken(source.source_id, id));
}

function sharingInstalls(streams: AudioSourceOption[]): string | null {
    const names = [...new Set(streams.flatMap((source) => source.installs_sharing_id ?? []))];
    return names.length > 1 ? names.join(', ') : null;
}

export interface SourceLines {
    /** The stream id, unless the stream sent no name and is already named by it. */
    id: string | null;
    /** The install, when another install sends the same id. */
    install: string | null;
}

/** What a detected stream shows beneath its name. */
export function sourceLines(source: AudioSourceOption): SourceLines {
    const id = source.source_id;
    const shared = Boolean(id) && (source.installs_sharing_id ?? []).length > 1;
    return {
        id: id && !sameLinkToken(id, source.source_name) ? id : null,
        install: shared ? source.source_node ?? null : null
    };
}

/** The picker's label: name, id and, when another install sends the same id, the install. */
export function sourceLinkLabel(source: AudioSourceOption): string {
    const lines = sourceLines(source);
    return [source.source_name, lines.id, lines.install].filter(Boolean).join(' · ');
}

function newest(times: Array<string | null | undefined>): string | null {
    return times.reduce<string | null>((latest, time) => (time && (!latest || Date.parse(time) > Date.parse(latest)) ? time : latest), null);
}

export function describeLinkToken(typed: string, sources: AudioSourceOption[]): LinkTokenDescription {
    const token = typed.trim();
    const streams = streamsWithId(token, sources);
    if (streams.length > 0) {
        const [first] = streams;
        const names = [...new Set(streams.map((source) => source.source_name))];
        const id = first.source_id ?? null;
        return {
            name: names.join(', '),
            id: names.every((name) => sameLinkToken(name, id)) ? null : id,
            install: sharingInstalls(streams),
            lastHeard: newest(streams.map((source) => source.last_seen))
        };
    }
    const times = sources.flatMap((source) => [
        ...(source.names ?? []).filter((name) => sameLinkToken(name.name, token)).map((name) => name.last_seen),
        ...(!source.source_id && sameLinkToken(source.mapping_value, token) ? [source.last_seen] : [])
    ]);
    return { name: token, id: null, install: null, lastHeard: newest(times) };
}

/**
 * Links by a name the server says one stream carried before its current one, while the camera
 * does not already link that stream's id.
 */
export function renamedLinks(tokens: string[], sources: AudioSourceOption[]): RenamedLink[] {
    return tokens.flatMap((token) => {
        const carriers = sources.filter((source) =>
            (source.names ?? []).some((name) => name.offer_link_by_id && sameLinkToken(name.name, token))
        );
        if (carriers.length !== 1) return [];
        const [source] = carriers;
        if (tokens.some((linked) => sameLinkToken(linked, source.mapping_value))) return [];
        return [{ token, source }];
    });
}

/**
 * The link with a renamed stream's id added right after its old name, unless the id is linked
 * already (compared exactly, once trimmed). Nothing else changes: the old name stays, so no call it
 * matches is lost, and the owner removes it once its last-heard date shows it has stopped.
 */
export function relinkByStreamId(tokens: string[], token: string, source: AudioSourceOption): string[] {
    const id = source.mapping_value.trim();
    if (tokens.some((linked) => linked.trim() === id)) return tokens;
    const at = tokens.indexOf(token);
    return at < 0 ? [...tokens, id] : [...tokens.slice(0, at + 1), id, ...tokens.slice(at + 1)];
}
