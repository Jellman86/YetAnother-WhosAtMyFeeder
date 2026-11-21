import { fetchModelActivity } from '../api/classifier';
import { reconcileActivity, type ActivityHint } from '../settings/model-activity';
import type { ActivityPhase } from '../settings/model-readiness';

export const ACTIVE_POLL_MS = 2000;
export const IDLE_POLL_MS = 15_000;

/**
 * Work in progress on a model: a download, or a check on this hardware.
 *
 * A model's own report says nothing of it. The server is where the work runs, so the server is the
 * authority (`GET /api/models/activity`), and this store keeps every surface reconciled with it:
 * Settings › Models, the wizard's review, About and Garden records all read the same phase, in this
 * tab and any other, and none of them can go on saying "Downloading" after the download has ended.
 *
 * It belongs to no page. A surface that states a model's readiness calls `watch()` while it is
 * shown, and the store asks the server for as long as anything is watching: often while work is in
 * progress, seldom otherwise. A page that starts work records a `hint` so its own button responds
 * at once; the hint lasts only until the server reports that model, or fails to in time.
 */
export class ModelActivityStore {
    private server = $state.raw<Record<string, ActivityPhase>>({});
    private hints = $state.raw<Record<string, ActivityHint>>({});
    private watchers = 0;
    private readonly listeners = new Set<() => void>();
    private timer: ReturnType<typeof setTimeout> | null = null;
    private reading = false;

    constructor(private readonly read: () => Promise<Record<string, ActivityPhase>> = fetchModelActivity) {}

    phase(modelId: string | null | undefined): ActivityPhase | null {
        if (!modelId) return null;
        return reconcileActivity(this.server, this.hints, Date.now()).phases[modelId] ?? null;
    }

    /** Every model with work in progress, for a page that has to resume showing its progress. */
    active(): Record<string, ActivityPhase> {
        return reconcileActivity(this.server, this.hints, Date.now()).phases;
    }

    /** Work started here just now, or with null work that ended here, ahead of the server's report. */
    hint(modelId: string, phase: ActivityPhase | null): void {
        const next = { ...this.hints };
        if (phase === null) delete next[modelId];
        else next[modelId] = { phase, at: Date.now() };
        this.hints = next;
        if (this.watchers > 0) this.schedule(ACTIVE_POLL_MS);
    }

    /**
     * Keeps the store reconciled while a surface shows a model's readiness. Returns the way to stop.
     * `onSettled` is called when work the server was reporting ends, so the surface can read the
     * model's own report again: what was "Downloading" is now ready, or failed.
     */
    watch(onSettled?: () => void): () => void {
        this.watchers += 1;
        if (onSettled) this.listeners.add(onSettled);
        if (this.watchers === 1) void this.reconcile();
        let stopped = false;
        return () => {
            if (stopped) return;
            stopped = true;
            if (onSettled) this.listeners.delete(onSettled);
            this.watchers -= 1;
            if (this.watchers === 0 && this.timer !== null) {
                clearTimeout(this.timer);
                this.timer = null;
            }
        };
    }

    private schedule(delay: number): void {
        if (this.timer !== null) clearTimeout(this.timer);
        this.timer = setTimeout(() => {
            this.timer = null;
            void this.reconcile();
        }, delay);
    }

    private async reconcile(): Promise<void> {
        if (this.reading) return;
        this.reading = true;
        const before = Object.keys(this.server);
        try {
            this.server = await this.read();
        } catch {
            // What cannot be read is not claimed: no phase, until the server answers again.
            this.server = {};
        } finally {
            this.reading = false;
        }
        this.hints = reconcileActivity(this.server, this.hints, Date.now()).hints;
        if (before.some((modelId) => !(modelId in this.server))) for (const settled of this.listeners) settled();
        if (this.watchers === 0) return;
        const busy = Object.keys(this.server).length > 0 || Object.keys(this.hints).length > 0;
        this.schedule(busy ? ACTIVE_POLL_MS : IDLE_POLL_MS);
    }
}

export const modelActivityStore = new ModelActivityStore();

/** The name Garden's automatic check model is reported under; it is not in the identification catalogue. */
export const GARDEN_CHECK_MODEL = 'garden-speciesnet-4.0.3a';
