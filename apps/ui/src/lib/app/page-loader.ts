/**
 * Cache a successful route import, share concurrent requests, and allow a failed
 * network/chunk request to be retried without refreshing the whole application.
 */
export function createRetryablePageLoader<Module>(
    importPage: () => Promise<Module>
): () => Promise<Module> {
    let cachedImport: Promise<Module> | null = null;

    return () => {
        if (!cachedImport) {
            cachedImport = importPage().catch((error: unknown) => {
                cachedImport = null;
                throw error;
            });
        }
        return cachedImport;
    };
}
