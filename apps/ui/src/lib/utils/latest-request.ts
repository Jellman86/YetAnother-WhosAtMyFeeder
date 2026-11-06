/**
 * A ticket for one read. It stays current until a newer read begins or the reads are
 * superseded, and only a current ticket may apply its result or clear the loading state.
 */
interface RequestTicket {
    isCurrent(): boolean;
}

/**
 * Only the newest read may apply its result.
 *
 * Responses can resolve in any order, and a request that was not aborted still resolves.
 * `begin()` supersedes every earlier ticket. `supersede()` does the same without starting a
 * read, for when what may be shown has changed (for example the public history moved on for a
 * visitor) and the rows already in flight must not land before the replacement read begins.
 */
export interface LatestRequest {
    begin(): RequestTicket;
    supersede(): void;
}

export function createLatestRequest(): LatestRequest {
    let generation = 0;
    return {
        begin(): RequestTicket {
            const ticket = ++generation;
            return { isCurrent: () => ticket === generation };
        },
        supersede(): void {
            generation += 1;
        }
    };
}
