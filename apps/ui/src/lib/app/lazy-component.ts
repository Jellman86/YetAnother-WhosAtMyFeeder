/**
 * Import a module on first use, for routes, dialogs, locales and heavy helpers alike: concurrent callers
 * share one import, a success is kept, and a failed chunk request is forgotten so an explicit retry
 * can recover without reloading the whole application.
 */
export function lazyComponent<Module>(importModule: () => Promise<Module>): () => Promise<Module> {
    let cachedImport: Promise<Module> | null = null;

    return () => {
        if (!cachedImport) {
            cachedImport = importModule().catch((error: unknown) => {
                cachedImport = null;
                throw error;
            });
        }
        return cachedImport;
    };
}
