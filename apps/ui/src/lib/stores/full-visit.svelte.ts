import { checkRecordingClipAvailable, fetchRecordingClip } from '../api';

export type FullVisitAvailabilityState = 'unknown' | 'checking' | 'available' | 'unavailable';
export type FullVisitFetchState = 'idle' | 'fetching' | 'ready' | 'failed';

export class FullVisitStore {
    availability = $state<Record<string, FullVisitAvailabilityState>>({});
    fetchState = $state<Record<string, FullVisitFetchState>>({});

    private probePromises = new Map<string, Promise<boolean>>();
    private fetchPromises = new Map<string, Promise<boolean>>();

    private markFetched(eventId: string): void {
        this.fetchState = { ...this.fetchState, [eventId]: 'ready' };
        this.availability = { ...this.availability, [eventId]: 'available' };
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

    async ensureAvailability(eventId: string, options: { refresh?: boolean } = {}): Promise<boolean> {
        const refresh = options.refresh === true;
        const current = this.getAvailability(eventId);
        if (!refresh) {
            if (current === 'available') return true;
            if (current === 'unavailable') return false;
        }

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
