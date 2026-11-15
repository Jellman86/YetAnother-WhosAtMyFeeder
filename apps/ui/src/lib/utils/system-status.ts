import type { ServiceConnections } from '../api/diagnostics';
import { connectionProblems } from './connection-health';
import type { LiveFeedState } from './live-feed-state';

/**
 * The words the sidebar's System status list shows for each measured state. Green is a thing
 * measured working, amber is work for a person, and neutral is off by choice or not yet known.
 * The tone is never the only cue: every state is a word, and each tone has its own dot shape.
 */
export type StatusTone = 'ok' | 'attention' | 'neutral';

export interface StatusText {
    key: string;
    fallback: string;
}

export interface StatusRow {
    id: 'feed' | 'audio' | 'alerts';
    tone: StatusTone;
    label: StatusText;
    state: StatusText;
    /** The full sentence, for the tooltip and the collapsed rail's accessible name. */
    detail: StatusText;
}

const text = (key: string, fallback: string): StatusText => ({ key: `status.${key}`, fallback });

const FEED_LABEL = text('row_feed', 'Frigate events');
const AUDIO_LABEL = text('row_audio', 'Audio');
const ALERTS_LABEL = text('row_alerts', 'Alerts');

const FEED_STATES: Record<LiveFeedState, Pick<StatusRow, 'tone' | 'state' | 'detail'>> = {
    live: {
        tone: 'ok',
        state: text('state_live', 'Live'),
        detail: text('feed_live', 'Receiving camera events')
    },
    connecting: {
        tone: 'neutral',
        state: text('state_waiting', 'Waiting for events'),
        detail: text('feed_connecting', 'Connecting to the MQTT broker')
    },
    broker_down: {
        tone: 'attention',
        state: text('state_not_connected', 'Not connected'),
        detail: text('feed_broker_down', 'Not receiving camera events. The MQTT broker is not connected.')
    },
    frigate_down: {
        tone: 'attention',
        state: text('state_frigate_down', 'Frigate not answering'),
        detail: text('feed_frigate_down', 'Frigate is not answering, so new detections cannot be saved')
    },
    app_only: {
        tone: 'neutral',
        state: text('state_connected', 'Connected'),
        detail: text('feed_app_only', 'Connected to YA-WAMF')
    },
    reconnecting: {
        tone: 'neutral',
        state: text('state_reconnecting', 'Reconnecting'),
        detail: text('feed_reconnecting', 'Reconnecting to YA-WAMF')
    }
};

export function feedRow(feed: LiveFeedState): StatusRow {
    return { id: 'feed', label: FEED_LABEL, ...FEED_STATES[feed] };
}

/** Audio detections arrive through the broker, so only a measured broker session is "Listening". */
export function audioRow(enabled: boolean, feed: LiveFeedState): StatusRow {
    if (!enabled) {
        return {
            id: 'audio',
            label: AUDIO_LABEL,
            tone: 'neutral',
            state: text('state_off', 'Off'),
            detail: text('audio_off', 'Audio analysis is off')
        };
    }
    if (feed === 'live' || feed === 'frigate_down') {
        return {
            id: 'audio',
            label: AUDIO_LABEL,
            tone: 'ok',
            state: text('state_listening', 'Listening'),
            detail: text('audio_listening', 'Listening for BirdNET-Go detections')
        };
    }
    if (feed === 'app_only') {
        return {
            id: 'audio',
            label: AUDIO_LABEL,
            tone: 'neutral',
            state: text('state_on', 'On'),
            detail: text('audio_on', 'Audio analysis is on')
        };
    }
    return {
        id: 'audio',
        label: AUDIO_LABEL,
        tone: 'neutral',
        state: text('state_not_listening', 'Not listening'),
        detail: text('audio_not_listening', 'Audio analysis is on, but the MQTT broker is not connected')
    };
}

/** Null when the setting was not read, as for a guest: the row is left out rather than guessed. */
export function alertsRow(active: boolean | null): StatusRow | null {
    if (active === null) return null;
    return {
        id: 'alerts',
        label: ALERTS_LABEL,
        tone: active ? 'ok' : 'neutral',
        state: active ? text('state_on', 'On') : text('state_off', 'Off'),
        detail: active
            ? text('alerts_on', 'Notifications are on')
            : text('alerts_off', 'Notifications are off')
    };
}

export interface HealthAttention {
    needsAttention: boolean;
    count: number;
}

/** The link asks for attention only for issues the Health page lists as open. */
export function healthAttention(openIssues: number | null): HealthAttention {
    const count = typeof openIssues === 'number' && Number.isFinite(openIssues) ? Math.max(0, Math.floor(openIssues)) : 0;
    return { needsAttention: count > 0, count };
}

/**
 * What the Health page lists as open: the failed connections of the workspace reading, then every
 * incident not yet resolved. Counted the same way here so the sidebar and the page cannot disagree.
 */
export function openHealthItems(connections: ServiceConnections | null, openIncidents: number): number {
    return connectionProblems(connections).length + Math.max(0, openIncidents);
}
