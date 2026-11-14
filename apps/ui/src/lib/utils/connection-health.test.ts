import { describe, expect, it } from 'vitest';
import type { ServiceConnections } from '../api/diagnostics';
import { connectionProblems, frigateCardStatus, healthVerdict, mqttCardStatus } from './connection-health';

function connections(mqtt: ServiceConnections['mqtt']['state'], frigate: ServiceConnections['frigate']['state']): ServiceConnections {
    return {
        mqtt: { state: mqtt, server: 'mqtt.invalid', port: 1883 },
        frigate: { state: frigate, url: 'http://frigate.invalid:5000', availability: 'unknown' },
        generated_at: '2026-11-13T18:00:00Z'
    };
}

describe('connection problems', () => {
    it('lists every connection that stops detections, broker first', () => {
        expect(connectionProblems(connections('disconnected', 'unreachable'))).toEqual(['mqtt_down', 'frigate_down']);
        expect(connectionProblems(connections('not_configured', 'reachable'))).toEqual(['mqtt_not_configured']);
        expect(connectionProblems(connections('stopped', 'unchecked'))).toEqual(['mqtt_stopped']);
    });

    it('finds none while both answer, or while they are still being reached', () => {
        expect(connectionProblems(connections('connected', 'reachable'))).toEqual([]);
        expect(connectionProblems(connections('connecting', 'unchecked'))).toEqual([]);
        expect(connectionProblems(null)).toEqual([]);
    });
});

describe('the Health verdict', () => {
    it('is never healthy while a connection is down, whatever the server status says', () => {
        expect(healthVerdict('ok', connections('disconnected', 'reachable'))).toBe('degraded');
        expect(healthVerdict('healthy', connections('connected', 'unreachable'))).toBe('degraded');
    });

    it('keeps a worse reported status', () => {
        expect(healthVerdict('critical', connections('disconnected', 'reachable'))).toBe('critical');
    });

    it('does not round unread connections up to healthy', () => {
        expect(healthVerdict('ok', null)).toBe('unknown');
        expect(healthVerdict('ok', connections('connected', 'reachable'))).toBe('ok');
    });
});

describe('the MQTT and Frigate cards', () => {
    it('lead with the connection state, and only show load while connected', () => {
        expect(mqttCardStatus(connections('disconnected', 'reachable'), 'normal')).toBe('disconnected');
        expect(mqttCardStatus(connections('connected', 'reachable'), 'normal')).toBe('connected');
        expect(mqttCardStatus(connections('connected', 'reachable'), 'high')).toBe('high');
        expect(mqttCardStatus(connections('connecting', 'reachable'), 'normal')).toBe('connecting');
        expect(mqttCardStatus(null, 'normal')).toBe('unknown');
    });

    it('say what Frigate last did', () => {
        expect(frigateCardStatus(connections('connected', 'unreachable'))).toBe('unreachable');
        expect(frigateCardStatus(connections('connected', 'unchecked'))).toBe('unchecked');
        expect(frigateCardStatus(null)).toBe('unknown');
    });
});
