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

    it('reads worker pools under ml or at the top level, as /health has reported them', () => {
        expect(readSignal({ ml: { worker_pools: { background: { circuit_open: true } } } }, 'ml.worker_pools.background.circuit_open')).toBe(true);
        expect(readSignal({ worker_pools: { background: { circuit_open: true } } }, 'ml.worker_pools.background.circuit_open')).toBe(true);
        expect(readSignal(null, 'video_classifier.circuit_open')).toBeUndefined();
    });
});
