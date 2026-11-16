import type { ActivityPhase } from '../settings/model-readiness';

/**
 * Work this app has started on a model and not finished: a download, or a check on this hardware.
 *
 * A model's own report says nothing of it, so the page that started the work used to be the only
 * one that knew. Whoever starts or watches the work records its phase here, and every surface that
 * states a model's readiness (Settings › Models, the wizard's review, About, Garden records) reads
 * the same phase.
 */
class ModelActivityStore {
    private phases = $state<Record<string, ActivityPhase>>({});

    phase(modelId: string | null | undefined): ActivityPhase | null {
        return modelId ? this.phases[modelId] ?? null : null;
    }

    /** Records the phase a model's work is in, or with null that the work is over. */
    set(modelId: string, phase: ActivityPhase | null): void {
        if ((this.phases[modelId] ?? null) === phase) return;
        const next = { ...this.phases };
        if (phase === null) delete next[modelId];
        else next[modelId] = phase;
        this.phases = next;
    }
}

export const modelActivityStore = new ModelActivityStore();

/** The key Garden's automatic check model is recorded under; it is not in the identification catalogue. */
export const GARDEN_CHECK_MODEL = 'garden-speciesnet-4.0.3a';
