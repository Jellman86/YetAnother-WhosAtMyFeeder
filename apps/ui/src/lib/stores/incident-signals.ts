/**
 * The health values a stateful incident is resolved from. The server fingerprints exactly these
 * (`INCIDENT_SIGNAL_PATHS` in backend/app/services/system_status.py, kept equal by a backend test),
 * so whenever one changes every owner page reads the incident workspace again. A predicate below
 * can read only a path on this list.
 */
export const INCIDENT_SIGNAL_PATHS = [
    'video_classifier.circuit_open',
    'ml.bird_finder.active',
    'ml.live_image.recovery_active',
    'ml.background_image.background_throttled',
    'ml.background_image.queued',
    'ml.worker_pools.live.circuit_open',
    'ml.worker_pools.background.circuit_open',
    'mqtt.frigate_availability.status',
    'media_storage.set_aside_pending'
] as const;

export type IncidentSignalPath = (typeof INCIDENT_SIGNAL_PATHS)[number];

function child(value: unknown, key: string): unknown {
    return value && typeof value === 'object' ? (value as Record<string, unknown>)[key] : undefined;
}

/** One signal's value in a `/health` reading. Worker pools may also sit at the top level. */
export function readSignal(health: Record<string, unknown> | null, path: IncidentSignalPath): unknown {
    const read = (root: unknown, parts: string[]): unknown => parts.reduce<unknown>(child, root);
    const parts = path.split('.');
    const value = read(health, parts);
    if (value === undefined && parts[0] === 'ml' && parts[1] === 'worker_pools') return read(health, parts.slice(1));
    return value;
}

interface StatefulIncident {
    component: string;
    reasons: readonly string[];
    /** Open, resolved, or null when the reading does not say. */
    isOpen(read: (path: IncidentSignalPath) => unknown): boolean | null;
}

/** Every incident whose state the health reading decides, and how. */
export const STATEFUL_INCIDENTS: readonly StatefulIncident[] = [
    { component: 'video_classifier', reasons: ['circuit_open'], isOpen: (read) => Boolean(read('video_classifier.circuit_open')) },
    {
        component: 'auto_video_classifier',
        reasons: ['video_circuit_open', 'video_circuit_opened'],
        isOpen: (read) => Boolean(read('video_classifier.circuit_open'))
    },
    {
        component: 'bird_finder',
        reasons: ['rfdetr_cpu_fallback'],
        isOpen: (read) => {
            const active = read('ml.bird_finder.active');
            return typeof active === 'boolean' ? active : null;
        }
    },
    { component: 'ml_live_image', reasons: ['recovery_active'], isOpen: (read) => Boolean(read('ml.live_image.recovery_active')) },
    {
        component: 'ml_background_image',
        reasons: ['throttled_by_live_pressure'],
        isOpen: (read) => Boolean(read('ml.background_image.background_throttled')) && Number(read('ml.background_image.queued') ?? 0) > 0
    },
    { component: 'ml_worker_live', reasons: ['circuit_open'], isOpen: (read) => Boolean(read('ml.worker_pools.live.circuit_open')) },
    { component: 'ml_worker_background', reasons: ['circuit_open'], isOpen: (read) => Boolean(read('ml.worker_pools.background.circuit_open')) },
    {
        // A restart blip stays in history as resolved; an outage stays open while Frigate is offline
        // and while its availability is unknown, so an unmeasured Frigate is never called healthy.
        component: 'mqtt_service',
        reasons: ['frigate_went_offline'],
        isOpen: (read) => {
            const availability = read('mqtt.frigate_availability.status');
            if (availability === 'online') return false;
            if (availability === 'offline') return true;
            return null;
        }
    },
    {
        // Photos or videos an interrupted cleanup set aside: open until the last one has gone back,
        // measured from disk on every storage check, so it closes by itself.
        component: 'media_cache',
        reasons: ['media_set_aside_unreturned'],
        isOpen: (read) => {
            const pending = read('media_storage.set_aside_pending');
            return typeof pending === 'number' ? pending > 0 : null;
        }
    }
];
