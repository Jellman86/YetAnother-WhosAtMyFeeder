import { describe, expect, it } from 'vitest';
import type { ServiceConnections } from '../api/diagnostics';
import { liveFeedState } from './live-feed-state';

function connections(mqtt: ServiceConnections['mqtt']['state'], frigate: ServiceConnections['frigate']['state']): ServiceConnections {
    return {
        mqtt: { state: mqtt, server: 'mqtt.invalid', port: 1883 },
        frigate: { state: frigate, url: 'http://frigate.invalid:5000', availability: 'unknown' },
        generated_at: '2026-11-13T18:00:00Z'
    };
}

describe('liveFeedState', () => {
    it('is live only when the page stream and the broker are both connected', () => {
        expect(liveFeedState(true, connections('connected', 'reachable'))).toBe('live');
        // Frigate not asked yet is no reason to stop calling the event feed live.
        expect(liveFeedState(true, connections('connected', 'unchecked'))).toBe('live');
    });

    it('never says live while the broker is down, whatever the page stream does', () => {
        expect(liveFeedState(true, connections('disconnected', 'reachable'))).toBe('broker_down');
        expect(liveFeedState(true, connections('not_configured', 'unchecked'))).toBe('broker_down');
        expect(liveFeedState(true, connections('stopped', 'reachable'))).toBe('broker_down');
    });

    it('reports a Frigate that does not answer even with the broker up', () => {
        expect(liveFeedState(true, connections('connected', 'unreachable'))).toBe('frigate_down');
    });

    it('reports a first broker attempt that is still running as connecting', () => {
        expect(liveFeedState(true, connections('connecting', 'unchecked'))).toBe('connecting');
    });

    it('claims only the page stream when the connections were not measured, as for a guest', () => {
        expect(liveFeedState(true, null)).toBe('app_only');
    });

    it('is reconnecting whenever the page stream is down', () => {
        expect(liveFeedState(false, connections('connected', 'reachable'))).toBe('reconnecting');
        expect(liveFeedState(false, null)).toBe('reconnecting');
    });
});
