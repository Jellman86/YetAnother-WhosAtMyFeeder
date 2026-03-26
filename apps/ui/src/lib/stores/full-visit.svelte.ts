import { checkRecordingClipAvailable, fetchRecordingClip } from '../api';

export type FullVisitAvailabilityState = 'unknown' | 'checking' | 'available' | 'unavailable';
export type FullVisitFetchState = 'idle' | 'fetching' | 'ready' | 'failed';
export type FullVisitClipVariant = 'event' | 'recording';

class FullVisitStore {
    availability = $state<Record<string, FullVisitAvailabilityState>>({});
    fetchState = $state<Record<string, FullVisitFetchState>>({});
    preferredClipVariantByEvent = $state<Record<string, FullVisitClipVariant>>({});

    private probePromises = new Map<string, Promise<boolean>>();
    private fetchPromises = new Map<string, Promise<boolean>>();

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
                const available = await checkRecordingClipAvailable(eventId);
                this.availability = {
                    ...this.availability,
                    [eventId]: available ? 'available' : 'unavailable'
                };
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
                this.fetchState = { ...this.fetchState, [eventId]: 'ready' };
                this.availability = { ...this.availability, [eventId]: 'available' };
                this.preferredClipVariantByEvent = {
                    ...this.preferredClipVariantByEvent,
                    [eventId]: 'recording'
                };
                return true;
            } catch (error) {
                const message = error instanceof Error ? error.message : '';
                if (message.includes('HTTP 404') || message.includes('not found')) {
                    this.availability = { ...this.availability, [eventId]: 'unavailable' };
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
