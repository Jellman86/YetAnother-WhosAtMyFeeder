import { describe, expect, it } from 'vitest';
import type { ServiceConnections } from '../api/diagnostics';
import { ServiceConnectionsStore } from './service_connections.svelte';

const reading: ServiceConnections = {
    mqtt: { state: 'disconnected', server: 'mqtt.invalid', port: 1883, last_error: 'refused' },
    frigate: { state: 'unreachable', url: 'http://frigate.invalid:5000', availability: 'unknown', last_failure: 'connection' },
    generated_at: '2026-11-13T18:00:00Z'
};

describe('ServiceConnectionsStore', () => {
    it('holds nothing until a reading arrives', () => {
        expect(new ServiceConnectionsStore().connections).toBeNull();
    });

    it('takes a reading from the pushed status or the workspace, and clears when access changes', () => {
        const store = new ServiceConnectionsStore();
        store.ingest(reading);
        expect(store.connections).toBe(reading);
        store.clear();
        expect(store.connections).toBeNull();
    });
});
