/**
 * How many scripts each lazily loaded view needs before it can draw, from the build's output
 * chunks: the entry and everything it imports, then each lazily loaded chunk on the way to the
 * view (Settings, then a tab) with everything those import, taking the costliest way when a view
 * is opened from more than one place. The build fails when a view needs
 * more than its budget (`vite.config.ts`), so a change that splits the bundle back into dozens of
 * small chunks is caught before it ships.
 *
 * Pure: the chunk graph is passed in, so the count is tested without a build.
 */

interface OutputChunk {
    readonly isEntry: boolean;
    /** The chunk holds an entry module's code; an entry chunk does unless that code was grouped elsewhere. */
    readonly holdsEntryCode?: boolean;
    readonly imports: readonly string[];
    readonly dynamicImports: readonly string[];
}

export type OutputChunks = Readonly<Record<string, OutputChunk>>;

function addWithImports(fileName: string, chunks: OutputChunks, into: Set<string>): void {
    const pending = [fileName];
    for (let current = pending.pop(); current !== undefined; current = pending.pop()) {
        if (into.has(current) || !chunks[current]) continue;
        into.add(current);
        pending.push(...chunks[current].imports);
    }
}

export function viewScriptCounts(chunks: OutputChunks): Array<{ view: string; scripts: number }> {
    const openedBy = new Map<string, string[]>();
    for (const [fileName, chunk] of Object.entries(chunks)) {
        for (const target of chunk.dynamicImports) openedBy.set(target, [...(openedBy.get(target) ?? []), fileName]);
    }
    const upFront = new Set<string>();
    for (const [fileName, chunk] of Object.entries(chunks)) if (chunk.isEntry) addWithImports(fileName, chunks, upFront);

    /**
     * The most scripts any way of reaching `view` needs: every chain of lazily loading chunks that
     * opens it is followed back to what loads up front, so a view opened cheaply from one place and
     * expensively from another is held to the expensive way.
     */
    function worst(view: string, onChain: ReadonlySet<string>, loaded: ReadonlySet<string>): number {
        const withView = new Set(loaded);
        addWithImports(view, chunks, withView);
        const openers = (openedBy.get(view) ?? []).filter((opener) => chunks[opener] && !onChain.has(opener));
        // Opened by code loaded up front, or by nothing further: this chain is complete.
        const further = openers.filter((opener) => !upFront.has(opener));
        if (further.length === 0) return withView.size;
        // An opener loaded up front completes one chain here; each other opener continues one.
        let most = further.length < openers.length ? withView.size : 0;
        const nextChain = new Set(onChain).add(view);
        for (const opener of further) most = Math.max(most, worst(opener, nextChain, withView));
        return most;
    }

    return [...openedBy.keys()]
        .filter((view) => chunks[view])
        .map((view) => ({ view, scripts: worst(view, new Set(), upFront) }));
}

/**
 * Chunks that statically import the chunk holding the entry's code. The entry awaits its locale
 * before it draws, so a chunk the entry is waiting for that imports the entry's code back can
 * never finish: the page stays blank with no error. The entry chunk itself may import it (it is
 * a stub when the entry's code was grouped elsewhere). The build fails on any other such import.
 */
export function chunksImportingAnEntry(chunks: OutputChunks): string[] {
    const holding = new Set(
        Object.entries(chunks).filter(([, chunk]) => chunk.holdsEntryCode ?? chunk.isEntry).map(([fileName]) => fileName)
    );
    return Object.entries(chunks)
        .filter(([, chunk]) => !chunk.isEntry)
        .flatMap(([fileName, chunk]) =>
            chunk.imports.filter((target) => holding.has(target) && target !== fileName).map((target) => `${fileName} imports ${target}`)
        );
}
