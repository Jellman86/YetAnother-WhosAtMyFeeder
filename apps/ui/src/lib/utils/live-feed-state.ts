import type { ServiceConnections } from '../api/diagnostics';

/**
 * What the "live" indicators may claim (layout-patterns 1.5). The page's own stream to this app
 * only says the page is connected; detections can arrive only while the broker session is up,
 * and be saved only while Frigate answers. Without a measurement (a guest, or before the first
 * read) nothing beyond the page stream is claimed.
 */
export type LiveFeedState = 'live' | 'connecting' | 'broker_down' | 'frigate_down' | 'app_only' | 'reconnecting';

export function liveFeedState(streamConnected: boolean, connections: ServiceConnections | null): LiveFeedState {
    if (!streamConnected) return 'reconnecting';
    if (!connections) return 'app_only';
    const mqtt = connections.mqtt.state;
    if (mqtt === 'connecting') return 'connecting';
    if (mqtt !== 'connected') return 'broker_down';
    if (connections.frigate.state === 'unreachable') return 'frigate_down';
    return 'live';
}
