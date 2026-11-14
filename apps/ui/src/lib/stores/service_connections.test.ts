import { describe, expect, it, vi } from 'vitest';
import type { ServiceConnections } from '../api/diagnostics';
import { ServiceConnectionsStore } from './service_connections.svelte';

const reading: ServiceConnections = {
    mqtt: { state: 'disconnected', server: 'mqtt.invalid', port: 1883, last_error: 'refused' },
    frigate: { state: 'unreachable', url: 'http://frigate.invalid:5000', availability: 'unknown', last_failure: 'connection' },
    generated_at: '2026-11-13T18:00:00Z'
};

describe('ServiceConnectionsStore', () => {
    it('holds nothing until it has read the server', () => {
        const store = new ServiceConnectionsStore({ fetch: vi.fn() });
        expect(store.connections).toBeNull();
    });

    it('shares one request between callers that ask at the same time', async () => {
        const fetch = vi.fn().mockResolvedValue(reading);
        const store = new ServiceConnectionsStore({ fetch });
        await Promise.all([store.refresh(), store.refresh()]);
        expect(fetch).toHaveBeenCalledTimes(1);
        expect(store.connections?.mqtt.state).toBe('disconnected');
    });

    it('forgets the last reading when a refresh fails, rather than showing it as current', async () => {
        const fetch = vi.fn().mockResolvedValueOnce(reading).mockRejectedValueOnce(new Error('HTTP 502'));
        const store = new ServiceConnectionsStore({ fetch });
        await store.refresh();
        await store.refresh();
        expect(store.connections).toBeNull();
    });

    it('takes a reading from elsewhere, and clears when access changes', () => {
        const store = new ServiceConnectionsStore({ fetch: vi.fn() });
        store.ingest(reading);
        expect(store.connections).toBe(reading);
        store.clear();
        expect(store.connections).toBeNull();
    });

    it('drops a reading that finishes after access changed', async () => {
        let resolve: (value: ServiceConnections) => void = () => {};
        const fetch = vi.fn().mockReturnValue(new Promise<ServiceConnections>((done) => { resolve = done; }));
        const store = new ServiceConnectionsStore({ fetch });
        const pending = store.refresh();
        store.clear();
        resolve(reading);
        await pending;
        expect(store.connections).toBeNull();
    });
});
