import type { AudioSourceOption } from '../api/audio';

/**
 * A camera's audio link is a list of BirdNET-Go source names and stream ids, matched literally by
 * the server. BirdNET-Go keeps a stream's id when the stream is renamed, so Settings links by id
 * where the source sends one, and shows the stream's current name beside it.
 */

export interface LinkTokenDescription {
    /** The first line: the stream's current name for a linked id, otherwise the token as typed. */
    name: string;
    /** The line beneath a linked id: the id, and the installs when more than one sends it. */
    detail: string | null;
    /** The newest visible call the token matches, as the API sent it; null when none does. */
    lastHeard: string | null;
}

export interface RenamedLink {
    token: string;
    source: AudioSourceOption;
}

/**
 * How the server compares a link (`normalize_mapping_key`): trimmed and case-folded, nothing
 * more. Upper then lower case folds as Python's casefold does for the letters that differ from
 * lower case, such as "ß" and "ss".
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

/** The tokens with each link once, the first spelling kept, in order. */
function distinct(tokens: string[]): string[] {
    const seen = new Set<string>();
    return tokens.filter((token) => {
        const key = fold(token);
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });
}

export function addLinkToken(tokens: string[], value: string): string[] {
    const next = value.trim();
    if (!next || tokens.some((token) => sameLinkToken(token, next))) return tokens;
    return [...tokens, next];
}

function streamsWithId(id: string, sources: AudioSourceOption[]): AudioSourceOption[] {
    return sources.filter((source) => source.source_id && sameLinkToken(source.source_id, id));
}

function installs(streams: AudioSourceOption[]): string | null {
    const names = [...new Set(streams.map((source) => source.source_node).filter((node): node is string => Boolean(node)))];
    return streams.length > 1 && names.length > 0 ? names.join(', ') : null;
}

/** The picker's label: name and id, and the install when another install sends the same id. */
export function sourceLinkLabel(source: AudioSourceOption, sources: AudioSourceOption[]): string {
    const id = source.source_id;
    if (!id || sameLinkToken(id, source.source_name)) return source.source_name;
    const shared = streamsWithId(id, sources).length > 1 && source.source_node;
    return shared ? `${source.source_name} · ${id} · ${source.source_node}` : `${source.source_name} · ${id}`;
}

/** The line beneath a detected stream's name: its id, and its install when another install sends the same id. */
export function sourceDetail(source: AudioSourceOption, sources: AudioSourceOption[]): string | null {
    const id = source.source_id;
    if (!id || sameLinkToken(id, source.source_name)) return null;
    return streamsWithId(id, sources).length > 1 && source.source_node ? `${id} · ${source.source_node}` : id;
}

function newest(times: Array<string | null | undefined>): string | null {
    return times.reduce<string | null>((latest, time) => (time && (!latest || Date.parse(time) > Date.parse(latest)) ? time : latest), null);
}

export function describeLinkToken(typed: string, sources: AudioSourceOption[]): LinkTokenDescription {
    const token = typed.trim();
    const streams = streamsWithId(token, sources);
    if (streams.length > 0) {
        const [first] = streams;
        const ids = installs(streams);
        return {
            name: [...new Set(streams.map((source) => source.source_name))].join(', '),
            detail: ids ? `${first.source_id} · ${ids}` : first.source_id ?? null,
            lastHeard: newest(streams.map((source) => source.last_seen))
        };
    }
    const times = sources.flatMap((source) => [
        ...(source.names ?? []).filter((name) => sameLinkToken(name.name, token)).map((name) => name.last_seen),
        ...(!source.source_id && sameLinkToken(source.mapping_value, token) ? [source.last_seen] : [])
    ]);
    return { name: token, detail: null, lastHeard: newest(times) };
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
 * The link with a renamed stream's id added right after its old name. The old name stays, so no
 * call it matches is lost; the owner removes it once its last-heard date shows it has stopped.
 */
export function relinkByStreamId(tokens: string[], token: string, source: AudioSourceOption): string[] {
    return distinct(tokens.flatMap((current) => (sameLinkToken(current, token) ? [current, source.mapping_value] : [current])));
}
