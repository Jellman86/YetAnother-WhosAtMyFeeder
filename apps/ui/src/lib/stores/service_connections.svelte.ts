import { fetchServiceConnections, type ServiceConnections } from '../api/diagnostics';
import { STATUS_SHARE_MS } from '../api/shared-read';

interface ServiceConnectionsStoreOptions {
    fetch?: () => Promise<ServiceConnections>;
    now?: () => number;
}

/** The owner's latest reading of the broker and Frigate connections, shared by the status tiles and Health. */
export class ServiceConnectionsStore {
    connections = $state.raw<ServiceConnections | null>(null);
    private readonly fetch: () => Promise<ServiceConnections>;
    private readonly now: () => number;
    private inFlight: Promise<void> | null = null;
    private generation = 0;
    private readAt = Number.NEGATIVE_INFINITY;

    constructor(options: ServiceConnectionsStoreOptions = {}) {
        this.fetch = options.fetch ?? (() => fetchServiceConnections());
        this.now = options.now ?? (() => Date.now());
    }

    /**
     * Reads the connections, unless a reading arrived moments ago: start-up and the live stream's
     * first connect both ask at once. `fresh` is for a change the server announced.
     */
    refresh({ fresh = false }: { fresh?: boolean } = {}): Promise<void> {
        if (this.inFlight && !fresh) return this.inFlight;
        if (!fresh && this.connections !== null && this.now() - this.readAt < STATUS_SHARE_MS) return Promise.resolve();
        const generation = ++this.generation;
        this.inFlight = (async () => {
            try {
                const reading = await this.fetch();
                if (generation === this.generation) {
                    this.connections = reading;
                    this.readAt = this.now();
                }
            } catch {
                // An old reading shown as current would claim a state nobody measured.
                if (generation === this.generation) this.connections = null;
            } finally {
                if (generation === this.generation) this.inFlight = null;
            }
        })();
        return this.inFlight;
    }

    ingest(reading: ServiceConnections): void {
        this.connections = reading;
        this.readAt = this.now();
    }

    clear(): void {
        this.generation += 1;
        this.inFlight = null;
        this.connections = null;
    }
}

export const serviceConnectionsStore = new ServiceConnectionsStore();
