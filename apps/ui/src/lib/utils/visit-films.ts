import { fetchVisitFilm } from '../api/about';

/**
 * One download per film, however many cards show it. The reel repeats its cards to loop, and
 * the film route forbids the browser from caching (a guest must not keep a copy once clips are
 * turned off), so each film is fetched once into an object URL that every card holding it
 * shares. The URL is released when the last card lets go.
 */
interface Entry {
    holders: number;
    url: Promise<string | null>;
    controller: AbortController;
}

const entries = new Map<string, Entry>();

export function holdVisitFilm(frigateEvent: string): Promise<string | null> {
    let entry = entries.get(frigateEvent);
    if (!entry) {
        const controller = new AbortController();
        const url = fetchVisitFilm(frigateEvent, controller.signal)
            .then((blob) => (blob && blob.size > 0 ? URL.createObjectURL(blob) : null))
            .catch(() => null);
        entry = { holders: 0, url, controller };
        entries.set(frigateEvent, entry);
    }
    entry.holders += 1;
    return entry.url;
}

export function releaseVisitFilm(frigateEvent: string): void {
    const entry = entries.get(frigateEvent);
    if (!entry) return;
    entry.holders -= 1;
    if (entry.holders > 0) return;
    entries.delete(frigateEvent);
    entry.controller.abort();
    void entry.url.then((url) => {
        if (url) URL.revokeObjectURL(url);
    });
}
