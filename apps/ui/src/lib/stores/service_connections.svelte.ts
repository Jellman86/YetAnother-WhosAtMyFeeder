import { fetchServiceConnections, type ServiceConnections } from '../api/diagnostics';

interface ServiceConnectionsStoreOptions {
    fetch?: () => Promise<ServiceConnections>;
}

/** The owner's latest reading of the broker and Frigate connections, shared by the status tiles and Health. */
export class ServiceConnectionsStore {
    connections = $state.raw<ServiceConnections | null>(null);
    private readonly fetch: () => Promise<ServiceConnections>;
    private inFlight: Promise<void> | null = null;
    private generation = 0;

    constructor(options: ServiceConnectionsStoreOptions = {}) {
        this.fetch = options.fetch ?? (() => fetchServiceConnections());
    }

    refresh(): Promise<void> {
        if (this.inFlight) return this.inFlight;
        const generation = this.generation;
        this.inFlight = (async () => {
            try {
                const reading = await this.fetch();
                if (generation === this.generation) this.connections = reading;
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
    }

    clear(): void {
        this.generation += 1;
        this.inFlight = null;
        this.connections = null;
    }
}

export const serviceConnectionsStore = new ServiceConnectionsStore();
