/**
 * Central coordinator that triggers background data refreshes when the user
 * navigates or returns to the browser tab.
 *
 * Stores register a refreshIfStale callback in their constructor.
 * App.svelte calls coordinator.onNavigate() inside navigate() and
 * coordinator.onVisibilityChange() inside the visibilitychange listener.
 */

type RefreshCallback = () => Promise<void> | void;

class RefreshCoordinator {
    private callbacks = new Set<RefreshCallback>();
    private debounceTimer: ReturnType<typeof setTimeout> | null = null;

    /** Register a store's refreshIfStale method. Returns an unregister function. */
    register(cb: RefreshCallback): () => void {
        this.callbacks.add(cb);
        return () => this.callbacks.delete(cb);
    }

    /** Call from navigate() in App.svelte after updating currentRoute. */
    onNavigate(): void {
        this.sweep();
    }

    /** Call from the visibilitychange handler in App.svelte when tab becomes visible. */
    onVisibilityChange(): void {
        if (document.hidden) return;
        this.sweep();
    }

    /** Call after SSE reconnects so stores catch up on any missed events. */
    onSseReconnect(): void {
        this.sweep();
    }

    private sweep(): void {
        // Debounce: navigation + visibilitychange can fire together; one sweep is enough.
        if (this.debounceTimer !== null) return;
        this.debounceTimer = setTimeout(() => {
            this.debounceTimer = null;
            for (const cb of this.callbacks) {
                void Promise.resolve(cb()).catch((err) => {
                    console.warn('[RefreshCoordinator] refreshIfStale error', err);
                });
            }
        }, 150);
    }
}

export const refreshCoordinator = new RefreshCoordinator();
