/**
 * Which output chunk a lazily loaded module belongs to.
 *
 * The bundler already keeps a module that only one lazily loaded view reaches inside that view's
 * chunk. What multiplies the scripts of a cold load is code several views share: left alone, the
 * bundler splits it into a small chunk for every combination of views that uses it. These rules
 * put that code into a few chunks by the kind of view that shares it (see `sharedChunkFor`);
 * everything the entry loads up front is one shell chunk (configured beside this, in
 * `vite.config.ts`).
 *
 * Pure: the bundler's module graph is passed in, so the rules are tested without a build.
 */

interface ModuleImporters {
    readonly importers: readonly string[];
    readonly dynamicImporters: readonly string[];
}

/** The part of the bundler's chunking context these rules read. */
export interface ModuleGraph {
    getModuleInfo(moduleId: string): ModuleImporters | null;
}

/**
 * Every lazily loaded entry (a page, a Settings tab, a dialog, a library) whose static imports
 * reach this module: one pass over its static importers, each module visited once, so a graph
 * whose import paths multiply costs no more than its size.
 */
function owningEntries(moduleId: string, graph: ModuleGraph): Set<string> {
    const owners = new Set<string>();
    const seen = new Set<string>([moduleId]);
    const pending = [moduleId];
    for (let current = pending.pop(); current !== undefined; current = pending.pop()) {
        const info = graph.getModuleInfo(current);
        if (!info) continue;
        if (info.dynamicImporters.length > 0) owners.add(current);
        for (const importer of info.importers) {
            if (seen.has(importer)) continue;
            seen.add(importer);
            pending.push(importer);
        }
    }
    return owners;
}

type ViewKind = 'settings' | 'setup' | 'dialogs' | 'views';

/** What kind of view a lazily loaded entry is; code one kind alone uses is loaded only with that kind. */
function viewKind(entryId: string): ViewKind {
    if (/[\\/]pages[\\/]Settings\.svelte$/.test(entryId) || /[\\/]components[\\/]settings[\\/]/.test(entryId)) return 'settings';
    if (/[\\/]pages[\\/]FirstRunWizard\.svelte$/.test(entryId) || /[\\/]components[\\/]setup[\\/]/.test(entryId)) return 'setup';
    // A component loaded on demand outside Settings and the wizard is a dialog or player opened from a page.
    if (/[\\/]src[\\/]lib[\\/]components[\\/][^\\/]+\.svelte$/.test(entryId)) return 'dialogs';
    return 'views';
}

/**
 * The chunk for code several lazily loaded entries share. Code only Settings and its tabs share
 * goes into `settings`, code only the setup wizard uses into `setup`, and code only dialogs share
 * into `dialogs`, each loaded when one of those opens. Code shared across kinds (pages, or a page
 * and a dialog) goes into `shared`. Null leaves a module to the bundler, which keeps code one
 * entry reaches inside that entry's chunk.
 */
export function sharedChunkFor(moduleId: string, graph: ModuleGraph): Exclude<ViewKind, 'views'> | 'shared' | null {
    const owners = owningEntries(moduleId, graph);
    if (owners.size < 2) return null;
    const kinds = new Set([...owners].map(viewKind));
    const [only] = kinds;
    return kinds.size === 1 && only !== 'views' ? only : 'shared';
}
