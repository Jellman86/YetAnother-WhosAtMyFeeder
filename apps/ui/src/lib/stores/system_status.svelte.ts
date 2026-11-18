import { fetchSystemStatus, type StatusTelemetry, type SubsystemKey, type SubsystemVerdict, type SystemStatus } from '../api/status';
import type { SystemTelemetry } from '../api/system';
import { startVisiblePoll, type PollDocument } from '../app/visible-poll';

/**
 * Without the live stream nothing announces a change, so the snapshot is read this often instead.
 * With it, the store makes no requests at all: the server pushes every change.
 */
export const STATUS_FALLBACK_READ_MS = 60_000;

/**
 * The server pushes the status at least every 15 seconds, and a stream that is down is replaced by
 * a read a minute. A status that has gone this long without a successor is out of date, however the
 * stream has behaved meanwhile (a proxy holding it, a server that dropped the subscriber, a stream
 * that reconnects without sending one): it says so and is read directly until one arrives.
 */
export const STATUS_STALE_AFTER_MS = 90_000;

/** Why the install is degraded, in the words the notification already has keys for. */
export type HealthNotificationCause = 'mqtt_down' | 'mqtt_not_configured' | 'frigate_down' | 'model_missing' | 'pipeline_critical' | 'other';

type StatusListener = (next: SystemStatus, previous: SystemStatus | null) => void;

interface SystemStatusStoreOptions {
    fetch?: (signal: AbortSignal) => Promise<SystemStatus>;
    tab?: PollDocument;
}

/**
 * The owner's one status reading. The shell, Health, the Dashboard and Settings › Models all read
 * it, so no two of them can show a different count or verdict for the same moment.
 */
export class SystemStatusStore {
    snapshot = $state.raw<SystemStatus | null>(null);
    /** True while the live stream is connected. */
    streamLive = $state(false);
    /** When the last snapshot was accepted, from a push or a read; null before the first. */
    receivedAt = $state<number | null>(null);
    /** No snapshot has been accepted for `STATUS_STALE_AFTER_MS`, counted from the last one or from start. */
    stale = $state(false);
    private readonly fetch: (signal: AbortSignal) => Promise<SystemStatus>;
    private readonly tab: PollDocument | undefined;
    private readonly listeners = new Set<StatusListener>();
    private inFlight: Promise<void> | null = null;
    private reading: AbortController | null = null;
    private generation = 0;
    private stopFallback: (() => void) | null = null;
    private active = false;
    // Plain copies of reactive state, so deciding about reads never subscribes the caller.
    private live = false;
    private isStale = false;
    private received = false;
    private deadline: ReturnType<typeof setTimeout> | null = null;

    constructor(options: SystemStatusStoreOptions = {}) {
        this.fetch = options.fetch ?? fetchSystemStatus;
        this.tab = options.tab;
    }

    /**
     * Takes a reading from the stream or a read. An older revision of the same backend is dropped,
     * so a slow read never overwrites a newer push; a restarted backend starts its count again.
     */
    ingest(next: SystemStatus): void {
        const previous = this.snapshot;
        if (previous && previous.startup_instance_id === next.startup_instance_id && next.revision < previous.revision) {
            return;
        }
        this.snapshot = next;
        this.receivedAt = Date.now();
        this.received = true;
        this.setStale(false);
        this.armDeadline(this.receivedAt);
        this.syncFallback();
        for (const listener of this.listeners) listener(next, previous);
    }

    /**
     * The one place freshness is counted from (the last accepted snapshot, or `start()` before one);
     * nothing else moves the deadline.
     */
    private armDeadline(since: number): void {
        if (this.deadline !== null) clearTimeout(this.deadline);
        this.deadline = null;
        if (!this.active) return;
        this.deadline = setTimeout(() => {
            this.deadline = null;
            this.setStale(true);
            void this.load();
            this.syncFallback();
        }, Math.max(0, since + STATUS_STALE_AFTER_MS - Date.now()));
    }

    private setStale(stale: boolean): void {
        this.isStale = stale;
        this.stale = stale;
    }

    /** Called with every accepted reading; returns the function that stops it. */
    subscribe(listener: StatusListener): () => void {
        this.listeners.add(listener);
        return () => this.listeners.delete(listener);
    }

    /** One read of the snapshot, shared by every caller asking at the same moment. */
    load(): Promise<void> {
        if (this.inFlight) return this.inFlight;
        const generation = this.generation;
        const controller = new AbortController();
        this.reading = controller;
        this.inFlight = (async () => {
            try {
                const reading = await this.fetch(controller.signal);
                if (generation === this.generation) this.ingest(reading);
            } catch {
                // The last reading stays; the stream or the next read replaces it.
            } finally {
                if (generation === this.generation) {
                    this.inFlight = null;
                    this.reading = null;
                }
            }
        })();
        return this.inFlight;
    }

    /** True while an owner's status is being followed; a reader can wait for it instead of asking. */
    get following(): boolean {
        return this.active;
    }

    /** Begin following the status for an owner: a first read, then the stream or the fallback read. */
    start(): void {
        this.active = true;
        this.armDeadline(Date.now());
        void this.load();
        this.syncFallback();
    }

    /** The stream connected or dropped. Only which reads are needed changes, never the deadline. */
    setStreamLive(live: boolean): void {
        this.live = live;
        this.streamLive = live;
        this.syncFallback();
    }

    /**
     * The fallback read runs unless a connected stream has delivered a status that is still fresh:
     * while the stream is down, before any status has arrived, or once the status is out of date.
     */
    private syncFallback(): void {
        const wanted = this.active && (!this.live || !this.received || this.isStale);
        if (wanted && this.stopFallback === null) {
            this.stopFallback = startVisiblePoll({
                read: () => this.load(),
                delayMs: () => STATUS_FALLBACK_READ_MS,
                readAtStart: false,
                tab: this.tab
            });
        } else if (!wanted && this.stopFallback !== null) {
            this.stopFallback();
            this.stopFallback = null;
        }
    }

    clear(): void {
        this.generation += 1;
        // A read made for the old session is abandoned, not left running beside the next one.
        this.reading?.abort();
        this.reading = null;
        this.inFlight = null;
        this.active = false;
        this.live = false;
        this.received = false;
        this.streamLive = false;
        this.setStale(false);
        if (this.deadline !== null) clearTimeout(this.deadline);
        this.deadline = null;
        this.syncFallback();
        this.snapshot = null;
        this.receivedAt = null;
    }
}

export const systemStatusStore = new SystemStatusStore();

export function verdictFor(snapshot: SystemStatus | null, key: SubsystemKey): SubsystemVerdict | null {
    return snapshot?.subsystems.find((verdict) => verdict.key === key) ?? null;
}

/** The notification's wording for a degraded install, from the same verdict Health shows. */
export function statusNotificationCause(snapshot: SystemStatus): HealthNotificationCause {
    const { cause, subsystem } = snapshot.overall;
    if (subsystem === 'mqtt' && cause === 'disconnected') return 'mqtt_down';
    if (subsystem === 'mqtt' && cause === 'not_configured') return 'mqtt_not_configured';
    if (subsystem === 'frigate' && cause === 'unreachable') return 'frigate_down';
    if (subsystem === 'classifier' && cause === 'model_missing') return 'model_missing';
    if (cause === 'pipeline_critical') return 'pipeline_critical';
    return 'other';
}

/** A pushed host sample in the shape the sidebar's CPU line already draws. */
export function telemetrySampleFrom(telemetry: StatusTelemetry): SystemTelemetry {
    const accelerator =
        telemetry.accelerator_kind && telemetry.accelerator_label
            ? {
                  kind: telemetry.accelerator_kind,
                  label: telemetry.accelerator_label,
                  utilization_percent: telemetry.accelerator_percent ?? null
              }
            : null;
    return {
        sampled_at: new Date(telemetry.sampled_at * 1000).toISOString(),
        cpu_percent: telemetry.cpu_percent ?? null,
        accelerator
    };
}
