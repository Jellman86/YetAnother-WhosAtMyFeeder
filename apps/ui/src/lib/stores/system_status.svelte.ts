import { fetchSystemStatus, type StatusTelemetry, type SubsystemKey, type SubsystemVerdict, type SystemStatus } from '../api/status';
import type { SystemTelemetry } from '../api/system';
import { startVisiblePoll, type PollDocument } from '../app/visible-poll';

/**
 * Without the live stream nothing announces a change, so the snapshot is read this often instead.
 * With it, the store makes no requests at all: the server pushes every change.
 */
export const STATUS_FALLBACK_READ_MS = 60_000;

/**
 * The server pushes the status at least every 15 seconds. A live stream that has brought none for
 * this long has stopped delivering it (a proxy holding it, or a server that dropped the subscriber),
 * so the status is said to be out of date and is read directly until a push arrives again.
 */
export const STATUS_STALE_AFTER_MS = 45_000;

/** Why the install is degraded, in the words the notification already has keys for. */
export type HealthNotificationCause = 'mqtt_down' | 'mqtt_not_configured' | 'frigate_down' | 'pipeline_critical' | 'other';

type StatusListener = (next: SystemStatus, previous: SystemStatus | null) => void;

interface SystemStatusStoreOptions {
    fetch?: () => Promise<SystemStatus>;
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
    /** When the last snapshot arrived, from a push or a read; null before the first. */
    receivedAt = $state<number | null>(null);
    /** No snapshot has arrived for longer than the server's push interval allows. */
    stale = $state(false);
    private readonly fetch: () => Promise<SystemStatus>;
    private readonly tab: PollDocument | undefined;
    private readonly listeners = new Set<StatusListener>();
    private inFlight: Promise<void> | null = null;
    private generation = 0;
    private stopFallback: (() => void) | null = null;
    private active = false;
    // A plain copy of `streamLive`, so deciding about the fallback read never subscribes the caller.
    private live = false;
    private isStale = false;
    // Plain, like `live`: whether any status has arrived since following began.
    private received = false;
    private staleTimer: ReturnType<typeof setTimeout> | null = null;

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
        const first = !this.received;
        this.received = true;
        this.markFresh();
        // The first status is what lets a connected stream be trusted, so the fallback can stop.
        if (first) this.syncFallback();
        for (const listener of this.listeners) listener(next, previous);
    }

    /**
     * How long a status may go without a successor before it is out of date: the push interval's
     * margin on a live stream (or before any status at all), and one fallback read later than that
     * while the stream is down and the status is being read once a minute.
     */
    private staleAfterMs(): number {
        return this.live || !this.received ? STATUS_STALE_AFTER_MS : STATUS_FALLBACK_READ_MS + STATUS_STALE_AFTER_MS;
    }

    private armWatchdog(): void {
        if (this.staleTimer !== null) clearTimeout(this.staleTimer);
        this.staleTimer = this.active
            ? setTimeout(() => {
                  this.staleTimer = null;
                  this.isStale = true;
                  this.stale = true;
                  // Read at once, then on the fallback cadence until a status arrives.
                  void this.load();
                  this.syncFallback();
              }, this.staleAfterMs())
            : null;
    }

    private markFresh(): void {
        this.receivedAt = Date.now();
        this.armWatchdog();
        if (this.isStale) {
            this.isStale = false;
            this.stale = false;
            this.syncFallback();
        }
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
        this.inFlight = (async () => {
            try {
                const reading = await this.fetch();
                if (generation === this.generation) this.ingest(reading);
            } catch {
                // The last reading stays; the stream or the next read replaces it.
            } finally {
                if (generation === this.generation) this.inFlight = null;
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
        // Armed before any status: a failed first read and a stream that connects but sends
        // nothing must still end in the status being called out of date and read again.
        this.armWatchdog();
        void this.load();
        this.syncFallback();
    }

    setStreamLive(live: boolean): void {
        const changed = live !== this.live;
        this.live = live;
        this.streamLive = live;
        // The time a status may stay unanswered depends on whether the stream is up.
        if (changed && this.active && !this.isStale) this.armWatchdog();
        this.syncFallback();
    }

    private syncFallback(): void {
        // A connected stream is trusted only once it, or a read, has brought a status.
        const wanted = this.active && (!this.live || this.isStale || !this.received);
        if (wanted && this.stopFallback === null) {
            this.stopFallback = startVisiblePoll({
                read: () => this.load(),
                delayMs: () => STATUS_FALLBACK_READ_MS,
                // The watchdog reads at once when the status goes out of date; this keeps the cadence.
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
        this.inFlight = null;
        this.active = false;
        this.live = false;
        this.streamLive = false;
        this.isStale = false;
        this.stale = false;
        this.received = false;
        if (this.staleTimer !== null) clearTimeout(this.staleTimer);
        this.staleTimer = null;
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
