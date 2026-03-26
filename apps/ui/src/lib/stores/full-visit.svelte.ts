import { checkRecordingClipAvailable, fetchRecordingClip } from '../api';

export type FullVisitAvailabilityState = 'unknown' | 'checking' | 'available' | 'unavailable';
export type FullVisitFetchState = 'idle' | 'fetching' | 'ready' | 'failed';
export type FullVisitClipVariant = 'event' | 'recording';

type FullVisitStorage = {
    getItem(key: string): string | null;
    setItem(key: string, value: string): void;
    removeItem(key: string): void;
};

const PERSISTED_FULL_VISIT_KEY = 'yawamf.fullVisitFetched.v1';
const MAX_PERSISTED_EVENTS = 500;

function getDefaultStorage(): FullVisitStorage | null {
    try {
        if (typeof globalThis !== 'undefined' && 'localStorage' in globalThis) {
            return globalThis.localStorage;
        }
    } catch {
        return null;
    }
    return null;
}

export class FullVisitStore {
    availability = $state<Record<string, FullVisitAvailabilityState>>({});
    fetchState = $state<Record<string, FullVisitFetchState>>({});
    preferredClipVariantByEvent = $state<Record<string, FullVisitClipVariant>>({});

    private probePromises = new Map<string, Promise<boolean>>();
    private fetchPromises = new Map<string, Promise<boolean>>();
    private readonly storage: FullVisitStorage | null;
    private persistedFetchedAt: Record<string, number> = {};

    constructor(storage: FullVisitStorage | null = getDefaultStorage()) {
        this.storage = storage;
        this.persistedFetchedAt = this.loadPersistedFetchedAt();
        const persistedEventIds = Object.keys(this.persistedFetchedAt);
        if (persistedEventIds.length > 0) {
            this.fetchState = Object.fromEntries(persistedEventIds.map((eventId) => [eventId, 'ready'])) as Record<string, FullVisitFetchState>;
            this.preferredClipVariantByEvent = Object.fromEntries(
                persistedEventIds.map((eventId) => [eventId, 'recording'])
            ) as Record<string, FullVisitClipVariant>;
        }
    }

    private loadPersistedFetchedAt(): Record<string, number> {
        if (!this.storage) return {};
        try {
            const raw = this.storage.getItem(PERSISTED_FULL_VISIT_KEY);
            if (!raw) return {};
            const parsed = JSON.parse(raw) as Record<string, unknown>;
            if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return {};
            const normalizedEntries = Object.entries(parsed)
                .filter(([eventId, value]) => typeof eventId === 'string' && Number.isFinite(Number(value)))
                .sort((a, b) => Number(b[1]) - Number(a[1]))
                .slice(0, MAX_PERSISTED_EVENTS)
                .map(([eventId, value]) => [eventId, Number(value)] as const);
            return Object.fromEntries(normalizedEntries);
        } catch {
            return {};
        }
    }

    private persistFetchedAt(): void {
        if (!this.storage) return;
        const entries = Object.entries(this.persistedFetchedAt)
            .sort((a, b) => b[1] - a[1])
            .slice(0, MAX_PERSISTED_EVENTS);
        const next = Object.fromEntries(entries);
        this.persistedFetchedAt = next;
        try {
            if (entries.length === 0) {
                this.storage.removeItem(PERSISTED_FULL_VISIT_KEY);
                return;
            }
            this.storage.setItem(PERSISTED_FULL_VISIT_KEY, JSON.stringify(next));
        } catch {
            // Best-effort only.
        }
    }

    private markFetched(eventId: string): void {
        this.fetchState = { ...this.fetchState, [eventId]: 'ready' };
        this.availability = { ...this.availability, [eventId]: 'available' };
        this.preferredClipVariantByEvent = {
            ...this.preferredClipVariantByEvent,
            [eventId]: 'recording'
        };
        this.persistedFetchedAt = {
            ...this.persistedFetchedAt,
            [eventId]: Date.now()
        };
        this.persistFetchedAt();
    }

    private clearFetched(eventId: string): void {
        const { [eventId]: _removedFetch, ...remainingFetch } = this.fetchState;
        const { [eventId]: _removedPreferred, ...remainingPreferred } = this.preferredClipVariantByEvent;
        this.fetchState = remainingFetch;
        this.preferredClipVariantByEvent = remainingPreferred;
        if (eventId in this.persistedFetchedAt) {
            const { [eventId]: _removedPersisted, ...remainingPersisted } = this.persistedFetchedAt;
            this.persistedFetchedAt = remainingPersisted;
            this.persistFetchedAt();
        }
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

    getPreferredClipVariant(eventId: string): FullVisitClipVariant {
        return this.preferredClipVariantByEvent[eventId] ?? 'event';
    }

    async ensureAvailability(eventId: string): Promise<boolean> {
        const current = this.getAvailability(eventId);
        if (current === 'available') return true;
        if (current === 'unavailable') return false;

        const inFlight = this.probePromises.get(eventId);
        if (inFlight) return inFlight;

        this.availability = { ...this.availability, [eventId]: 'checking' };

        const probePromise = (async () => {
            try {
                const { available, fetched } = await checkRecordingClipAvailable(eventId);
                this.availability = {
                    ...this.availability,
                    [eventId]: available ? 'available' : 'unavailable'
                };
                if (available && fetched) {
                    this.markFetched(eventId);
                } else if (!available) {
                    this.clearFetched(eventId);
                }
                if (!available && this.getPreferredClipVariant(eventId) === 'recording' && !this.isFetched(eventId)) {
                    this.preferredClipVariantByEvent = {
                        ...this.preferredClipVariantByEvent,
                        [eventId]: 'event'
                    };
                }
                return available;
            } catch {
                this.availability = { ...this.availability, [eventId]: 'unavailable' };
                return false;
            } finally {
                this.probePromises.delete(eventId);
            }
        })();

        this.probePromises.set(eventId, probePromise);
        return probePromise;
    }

    async fetchFullVisit(eventId: string): Promise<boolean> {
        if (this.isFetched(eventId)) return true;

        const inFlight = this.fetchPromises.get(eventId);
        if (inFlight) return inFlight;

        this.fetchState = { ...this.fetchState, [eventId]: 'fetching' };

        const fetchPromise = (async () => {
            try {
                await fetchRecordingClip(eventId);
                this.markFetched(eventId);
                return true;
            } catch (error) {
                const message = error instanceof Error ? error.message : '';
                if (message.includes('HTTP 404') || message.includes('not found')) {
                    this.availability = { ...this.availability, [eventId]: 'unavailable' };
                    this.clearFetched(eventId);
                }
                this.fetchState = { ...this.fetchState, [eventId]: 'failed' };
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
