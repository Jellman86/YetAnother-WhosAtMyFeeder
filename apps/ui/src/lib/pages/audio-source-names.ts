/**
 * Audio history lists each BirdNET-Go source once, by the id BirdNET-Go derives from its stream
 * address or sound card, so a rename keeps one entry (#1111). Two entries can still carry the same
 * name, when a stream's address changed and BirdNET-Go gave it a new id; those are the names whose
 * entries need their id beside them to be told apart.
 */
export function namesListedMoreThanOnce(sources: readonly { source_name: string }[]): Set<string> {
    const seen = new Set<string>();
    const shared = new Set<string>();
    for (const source of sources) {
        const name = sourceNameKey(source.source_name);
        if (seen.has(name)) shared.add(name);
        seen.add(name);
    }
    return shared;
}

/** How a source name is compared: BirdNET-Go names differ in case only by accident. */
export function sourceNameKey(name: string): string {
    return name.trim().toLocaleLowerCase();
}
