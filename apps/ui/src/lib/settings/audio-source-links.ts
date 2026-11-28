import type { AudioSourceOption } from '../api/audio';

/**
 * A camera's audio link is a list of BirdNET-Go source names and stream ids, matched literally by
 * the server. BirdNET-Go keeps a stream's id when the stream is renamed, so Settings links by id
 * where the source sends one, and shows the stream's current name beside it.
 */

export interface LinkTokenDescription {
    /** What the chip says: "Name · id" for a linked stream id, otherwise the token as typed. */
    text: string;
    /** When the name or stream was last heard, as the API sent it; null for a token no source matches. */
    lastHeard: string | null;
}

export interface RenamedLink {
    token: string;
    source: AudioSourceOption;
}

/** How the server compares a link: case and surrounding or repeated whitespace ignored. */
function fold(value: string | null | undefined): string {
    return (value ?? '').trim().split(/\s+/).join(' ').toLocaleLowerCase();
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
    if (!next || tokens.some((token) => fold(token) === fold(next))) return tokens;
    return [...tokens, next];
}

export function sourceLinkLabel(source: AudioSourceOption): string {
    const id = source.source_id;
    return id && fold(id) !== fold(source.source_name) ? `${source.source_name} · ${id}` : source.source_name;
}

export function describeLinkToken(typed: string, sources: AudioSourceOption[]): LinkTokenDescription {
    const token = typed.trim();
    const key = fold(token);
    const byId = sources.find((source) => source.source_id && fold(source.source_id) === key);
    if (byId) return { text: sourceLinkLabel(byId), lastHeard: byId.last_seen };
    const byName = sources.find((source) => fold(source.source_name) === key);
    if (byName) return { text: token, lastHeard: byName.last_seen };
    for (const source of sources) {
        const earlier = (source.earlier_names ?? []).find((name) => fold(name.name) === key);
        if (earlier) return { text: token, lastHeard: earlier.last_seen };
    }
    return { text: token, lastHeard: null };
}

/**
 * Links by a name one stream carried before its current one. A name that is any source's current
 * name, or that two streams carried, is left alone: it still matches, or cannot be told apart.
 */
export function renamedLinks(tokens: string[], sources: AudioSourceOption[]): RenamedLink[] {
    const linked = new Set(tokens.map(fold));
    return tokens.flatMap((token) => {
        const key = fold(token);
        if (sources.some((source) => fold(source.source_name) === key || fold(source.mapping_value) === key)) return [];
        const carriers = sources.filter(
            (source) => source.source_id && (source.earlier_names ?? []).some((name) => fold(name.name) === key)
        );
        if (carriers.length !== 1) return [];
        const [source] = carriers;
        if (linked.has(fold(source.mapping_value))) return [];
        return [{ token, source }];
    });
}

/**
 * The link with a renamed stream's id in place of its old name. Calls stored before BirdNET-Go sent
 * ids match by name only, so the old name stays beside the id while any such call carries it.
 */
export function relinkByStreamId(tokens: string[], token: string, source: AudioSourceOption): string[] {
    const key = fold(token);
    const keepName = (source.earlier_names ?? []).some((name) => fold(name.name) === key && name.has_calls_without_id);
    return tokens.flatMap((current) => {
        if (fold(current) !== key) return [current];
        return keepName ? [current, source.mapping_value] : [source.mapping_value];
    });
}
