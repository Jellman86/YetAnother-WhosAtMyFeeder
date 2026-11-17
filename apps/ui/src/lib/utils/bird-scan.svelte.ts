import { untrack } from 'svelte';
import { fetchBirdScan, startBirdScan } from '../api/media';
import { birdScanMediaVersion, createBirdScanController, type BirdScanView } from './bird-scan-controller';
import { birdScanStandingReason, birdScanUnavailableReason } from './bird-scan-standing';

/** The photograph a scan is bound to; null when the viewer may not scan at all. */
export interface BirdScanTarget {
    eventId: string;
    candidateId: string | null;
    imageVersion: string | null;
}

const IDLE: BirdScanView = { response: null, pending: false, readError: false, startUnconfirmed: false };

/**
 * The one owner of a photograph's scan: its requests and polling, what is known about it, and why it
 * cannot run. The scan row and the record both read it, so nothing copies its state from one to the
 * other. Create it while a component initialises; its lifetime is that component's.
 */
export class BirdScan {
    view = $state<BirdScanView>({ ...IDLE });
    readonly #target: () => BirdScanTarget | null;
    #controller: ReturnType<typeof createBirdScanController> | null = null;

    readonly mediaRevision: string | null;
    /** A whole frame and an image revision to bind a scan to. */
    readonly ready: boolean;
    readonly active: boolean;
    readonly unavailableReason: string | null;
    /** Why the finder cannot run, when that holds until something elsewhere changes; null otherwise. */
    readonly standingReason: string | null;
    /** What the poller is bound to, compared by value so an equal recomputation never restarts it. */
    readonly #binding: string | null;

    constructor(target: () => BirdScanTarget | null, oncompleted: (eventId: string, candidateId: string) => void) {
        this.#target = target;
        this.mediaRevision = $derived(birdScanMediaVersion(this.#target()?.imageVersion ?? null));
        this.ready = $derived(Boolean(this.#target()?.candidateId && this.mediaRevision));
        this.active = $derived(this.view.response?.status === 'queued' || this.view.response?.status === 'running');
        this.unavailableReason = $derived(birdScanUnavailableReason(this.#target()?.candidateId ?? null, this.mediaRevision, this.view.response));
        this.standingReason = $derived(
            this.#target() ? birdScanStandingReason(this.unavailableReason, { active: this.active, readError: this.view.readError }) : null
        );
        this.#binding = $derived.by(() => {
            const current = this.#target();
            return current?.candidateId && this.mediaRevision ? JSON.stringify([current.eventId, current.candidateId, this.mediaRevision]) : null;
        });
        // The scan runs on the server and is polled: a system outside Svelte, set up per photograph.
        $effect(() => {
            const binding = this.#binding;
            return untrack(() => {
                this.view = { ...IDLE };
                this.#controller = null;
                if (!binding) return;
                const [eventId, candidateId, revision] = JSON.parse(binding) as [string, string, string];
                const controller = createBirdScanController({
                    eventId,
                    candidateId,
                    read: (signal) => fetchBirdScan(eventId, candidateId, revision, signal),
                    start: (force, signal) => startBirdScan(eventId, candidateId, revision, force, signal),
                    onChange: (next) => { this.view = next; },
                    onCompleted: () => oncompleted(eventId, candidateId),
                    isVisible: () => !document.hidden
                });
                this.#controller = controller;
                const visibility = (): void => { void controller.visibilityChanged(); };
                document.addEventListener('visibilitychange', visibility);
                void controller.refresh();
                return () => {
                    controller.dispose();
                    document.removeEventListener('visibilitychange', visibility);
                    if (this.#controller === controller) this.#controller = null;
                };
            });
        });
    }

    refresh(): Promise<void> {
        return this.#controller?.refresh() ?? Promise.resolve();
    }

    start(force: boolean): Promise<void> {
        return this.#controller?.start(force) ?? Promise.resolve();
    }
}
