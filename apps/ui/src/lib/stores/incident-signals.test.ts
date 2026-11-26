import { describe, expect, it } from 'vitest';
import { INCIDENT_SIGNAL_PATHS, STATEFUL_INCIDENTS, readSignal, type IncidentSignalPath } from './incident-signals';

describe('incident signals', () => {
    it('are exactly the paths the stateful incidents are resolved from', () => {
        const read = new Set<IncidentSignalPath>();
        for (const incident of STATEFUL_INCIDENTS) {
            // A reading where every signal is set, so every branch of every predicate reads.
            incident.isOpen((path) => {
                read.add(path);
                return path.endsWith('.queued') ? 1 : true;
            });
        }
        expect([...read].sort()).toEqual([...INCIDENT_SIGNAL_PATHS].sort());
    });

    it('keeps the set-aside media incident open until the last file has gone back', () => {
        const incident = STATEFUL_INCIDENTS.find((candidate) => candidate.component === 'media_cache');
        const reading = (pending: unknown) => (path: IncidentSignalPath) =>
            path === 'media_storage.set_aside_pending' ? pending : undefined;
        expect(incident?.reasons).toEqual(['media_set_aside_unreturned']);
        expect(incident?.isOpen(reading(2))).toBe(true);
        expect(incident?.isOpen(reading(0))).toBe(false);
        // An older backend that does not report the count leaves the incident as recorded.
        expect(incident?.isOpen(reading(undefined))).toBeNull();
    });

    it('reads worker pools under ml or at the top level, as /health has reported them', () => {
        expect(readSignal({ ml: { worker_pools: { background: { circuit_open: true } } } }, 'ml.worker_pools.background.circuit_open')).toBe(true);
        expect(readSignal({ worker_pools: { background: { circuit_open: true } } }, 'ml.worker_pools.background.circuit_open')).toBe(true);
        expect(readSignal(null, 'video_classifier.circuit_open')).toBeUndefined();
    });
});
