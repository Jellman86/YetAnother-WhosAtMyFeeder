import type { ServiceConnections } from '../api/diagnostics';
import { statusTone } from './status-tone';

/** A connection that stops new detections, in the order an owner should fix them. */
export type ConnectionProblem = 'mqtt_down' | 'mqtt_not_configured' | 'mqtt_stopped' | 'frigate_down';

export function connectionProblems(connections: ServiceConnections | null): ConnectionProblem[] {
    if (!connections) return [];
    const problems: ConnectionProblem[] = [];
    const mqtt = connections.mqtt.state;
    if (mqtt === 'disconnected') problems.push('mqtt_down');
    else if (mqtt === 'not_configured') problems.push('mqtt_not_configured');
    else if (mqtt === 'stopped') problems.push('mqtt_stopped');
    if (connections.frigate.state === 'unreachable') problems.push('frigate_down');
    return problems;
}

const SEVERITY = { healthy: 0, unknown: 1, running: 1, attention: 2, failure: 3 } as const;

/**
 * The page's verdict. The server's status covers what runs inside this app; a broker or Frigate
 * that is down is a fault too, and connections that could not be read are not counted as fine.
 */
export function healthVerdict(reported: string, connections: ServiceConnections | null): string {
    const tone = statusTone(reported);
    if (connectionProblems(connections).length > 0) {
        return SEVERITY[tone] > SEVERITY.attention ? reported : 'degraded';
    }
    if (connections === null && tone === 'healthy') return 'unknown';
    return reported;
}

export function mqttCardStatus(connections: ServiceConnections | null, pressure: string): string {
    if (!connections) return 'unknown';
    const state = connections.mqtt.state;
    if (state !== 'connected') return state;
    const load = pressure.trim().toLowerCase();
    return load === 'high' || load === 'critical' ? load : 'connected';
}

export function frigateCardStatus(connections: ServiceConnections | null): string {
    return connections ? connections.frigate.state : 'unknown';
}
