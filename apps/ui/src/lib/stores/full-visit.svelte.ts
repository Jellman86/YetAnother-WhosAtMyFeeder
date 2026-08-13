import { checkRecordingClipAvailable, fetchRecordingClip } from '../api';

export type FullVisitAvailabilityState = 'unknown' | 'checking' | 'available' | 'unavailable';
export type FullVisitFetchState = 'idle' | 'fetching' | 'ready' | 'partial' | 'failed';

interface FullVisitStoreOptions {
    maxEntries?: number;
    reprobeDelayMs?: number;
}

export class FullVisitStore {
    availability = $state<Record<string, FullVisitAvailabilityState>>({});
    fetchState = $state<Record<string, FullVisitFetchState>>({});

    private probePromises = new Map<string, Promise<boolean>>();
    private fetchPromises = new Map<string, Promise<boolean>>();
    private reprobeTimers = new Map<string, ReturnType<typeof setTimeout>>();
    private reprobeAttempted = new Set<string>();
    private recentEvents = new Map<string, true>();
    private readonly maxEntries: number;
    private readonly reprobeDelayMs: number;

    constructor(options: FullVisitStoreOptions = {}) {
        this.maxEntries = Math.max(1, Math.floor(options.maxEntries ?? 250));
        this.reprobeDelayMs = Math.max(0, Math.floor(options.reprobeDelayMs ?? 8000));
    }

    private touch(eventId: string): void {
        this.recentEvents.delete(eventId);
        this.recentEvents.set(eventId, true);
        this.prune();
    }

    private prune(): void {
        if (this.recentEvents.size <= this.maxEntries) return;
        const nextAvailability = { ...this.availability };
        const nextFetchState = { ...this.fetchState };
        let changed = false;

        while (this.recentEvents.size > this.maxEntries) {
            const oldestEventId = this.recentEvents.keys().next().value;
            if (typeof oldestEventId !== 'string') break;
            this.recentEvents.delete(oldestEventId);
            delete nextAvailability[oldestEventId];
            delete nextFetchState[oldestEventId];
            this.cancelReprobe(oldestEventId);
            this.reprobeAttempted.delete(oldestEventId);
            changed = true;
        }

        if (changed) {
            this.availability = nextAvailability;
            this.fetchState = nextFetchState;
        }
    }

    private setAvailability(eventId: string, state: FullVisitAvailabilityState): void {
        this.touch(eventId);
        this.availability = { ...this.availability, [eventId]: state };
    }

    private setFetchState(eventId: string, state: FullVisitFetchState): void {
        this.touch(eventId);
        this.fetchState = { ...this.fetchState, [eventId]: state };
    }

    private markFetched(eventId: string): void {
        this.setFetchState(eventId, 'ready');
        this.setAvailability(eventId, 'available');
    }

    private clearFetched(eventId: string): void {
        const { [eventId]: _removedFetch, ...remainingFetch } = this.fetchState;
        this.fetchState = remainingFetch;
    }

    getAvailability(eventId: string): FullVisitAvailabilityState {
        return this.availability[eventId] ?? 'unknown';
    }

    isAvailable(eventId: string): boolean {
        return this.getAvailability(eventId) === 'available';
    }

    getFetchState(eventId: string): FullVisitFetchState {
        return this.fetchState[eventId] ?? 'idle';
    }

    isFetched(eventId: string): boolean {
        return this.getFetchState(eventId) === 'ready';
    }

    private scheduleReprobe(eventId: string): void {
        if (this.reprobeTimers.has(eventId) || this.reprobeAttempted.has(eventId)) return;
        this.reprobeAttempted.add(eventId);
        const timer = setTimeout(() => {
            this.reprobeTimers.delete(eventId);
            void this.ensureAvailability(eventId, { refresh: true });
        }, this.reprobeDelayMs);
        this.reprobeTimers.set(eventId, timer);
    }

    private cancelReprobe(eventId: string): void {
        const timer = this.reprobeTimers.get(eventId);
        if (timer !== undefined) {
            clearTimeout(timer);
            this.reprobeTimers.delete(eventId);
        }
    }

    async ensureAvailability(eventId: string, options: { refresh?: boolean; autoFetch?: boolean } = {}): Promise<boolean> {
        this.touch(eventId);
        const refresh = options.refresh === true;
        const autoFetch = options.autoFetch === true;
        const current = this.getAvailability(eventId);
        if (!refresh) {
            if (current === 'available') {
                if (autoFetch && !this.isFetched(eventId)) {
                    this.startAutomaticFetch(eventId);
                }
                return true;
            }
            if (current === 'unavailable') return false;
        }

        const inFlight = this.probePromises.get(eventId);
        if (inFlight) {
            if (autoFetch) {
                void inFlight.then((available) => {
                    if (available && !this.isFetched(eventId)) this.startAutomaticFetch(eventId);
                });
            }
            return inFlight;
        }

        this.setAvailability(eventId, 'checking');

        const probePromise = (async () => {
            try {
                const { available, fetched } = await checkRecordingClipAvailable(eventId);
                this.setAvailability(eventId, available ? 'available' : 'unavailable');
                if (available && fetched) {
                    this.markFetched(eventId);
                    this.cancelReprobe(eventId);
                } else if (!available) {
                    this.clearFetched(eventId);
                    this.cancelReprobe(eventId);
                } else if (autoFetch) {
                    // Available in Frigate but not cached locally — auto-fetch now.
                    this.cancelReprobe(eventId);
                    this.startAutomaticFetch(eventId);
                } else {
                    // Available in Frigate but not yet cached locally.
                    // The backend may be in the middle of auto-caching — schedule
                    // a single re-probe so the UI corrects itself shortly after.
                    this.scheduleReprobe(eventId);
                }
                return available;
            } catch {
                this.setAvailability(eventId, 'unavailable');
                return false;
            } finally {
                this.probePromises.delete(eventId);
            }
        })();

        this.probePromises.set(eventId, probePromise);
        return probePromise;
    }

    private startAutomaticFetch(eventId: string): void {
        void this.fetchFullVisit(eventId).catch(() => undefined);
    }

    async fetchFullVisit(eventId: string): Promise<boolean> {
        this.touch(eventId);
        if (this.isFetched(eventId)) return true;

        const inFlight = this.fetchPromises.get(eventId);
        if (inFlight) return inFlight;

        this.setFetchState(eventId, 'fetching');

        const fetchPromise = (async () => {
            try {
                const result = await fetchRecordingClip(eventId);
                this.setAvailability(eventId, 'available');
                this.cancelReprobe(eventId);
                if (result.recording_state === 'complete') {
                    this.markFetched(eventId);
                    return true;
                }
                this.setFetchState(eventId, 'partial');
                return false;
            } catch (error) {
                const message = error instanceof Error ? error.message : '';
                if (message.includes('HTTP 404') || message.includes('not found')) {
                    this.setAvailability(eventId, 'unavailable');
                    this.clearFetched(eventId);
                }
                this.setFetchState(eventId, 'failed');
                throw error;
            } finally {
                this.fetchPromises.delete(eventId);
            }
        })();

        this.fetchPromises.set(eventId, fetchPromise);
        return fetchPromise;
    }
}

export const fullVisitStore = new FullVisitStore();
