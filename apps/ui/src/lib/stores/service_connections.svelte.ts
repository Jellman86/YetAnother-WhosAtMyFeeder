import type { ServiceConnections } from '../api/diagnostics';

/**
 * The owner's latest reading of the broker and Frigate connections, shared by the status tiles and
 * Health. It arrives with the pushed status snapshot and with the Health workspace; nothing here reads.
 */
export class ServiceConnectionsStore {
    connections = $state.raw<ServiceConnections | null>(null);

    ingest(reading: ServiceConnections): void {
        this.connections = reading;
    }

    clear(): void {
        this.connections = null;
    }
}

export const serviceConnectionsStore = new ServiceConnectionsStore();
