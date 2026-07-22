import { fetchSetupState, type SetupState, type SetupSectionId, type SetupSectionStatus } from '../api/setup';

/**
 * Ordered wizard steps. Most map to a backend config section (whose readiness drives the
 * section map); `welcome` and `review` are flow-only. Keeping the sequence here — separate
 * from the step components — lets the shell own navigation/progress and the steps stay dumb.
 */
export interface WizardStep {
    id: string;
    /** Backend section this step configures, if any (for readiness markers). */
    section: SetupSectionId | null;
    /** Optional steps can be skipped without leaving the section in an "attention" state. */
    optional: boolean;
}

export const WIZARD_STEPS: readonly WizardStep[] = [
    { id: 'welcome', section: null, optional: false },
    { id: 'account', section: 'account', optional: false },
    { id: 'connection', section: 'connection', optional: false },
    { id: 'cameras', section: 'cameras', optional: false },
    { id: 'model', section: 'model', optional: false },
    { id: 'quality', section: 'quality', optional: true },
    { id: 'integrations', section: 'integrations', optional: true },
    { id: 'history', section: null, optional: true },
    { id: 'telemetry', section: null, optional: true },
    { id: 'review', section: null, optional: false }
];

export type WizardMode = 'first_run' | 'rerun';

/**
 * Shared wizard navigation + section readiness. The store holds no config itself — each step
 * reads/writes the real config through the settings API — so re-running a single step never
 * touches unrelated sections.
 */
class SetupWizardStore {
    steps = WIZARD_STEPS;
    mode = $state<WizardMode>('first_run');
    index = $state(0);
    setupState = $state<SetupState | null>(null);
    active = $state(false);
    refreshing = $state(false);
    refreshFailed = $state(false);
    private refreshPromise: Promise<void> | null = null;

    /** Open the wizard. First-run mode starts at the beginning; re-run opens on the section map. */
    open(mode: WizardMode = 'first_run'): void {
        this.mode = mode;
        this.index = mode === 'first_run' ? 0 : this.indexOf('review'); // re-run shows review/map first
        this.active = true;
        void this.refresh();
    }

    close(): void {
        this.active = false;
    }

    async refresh(): Promise<void> {
        if (this.refreshPromise) return this.refreshPromise;
        this.refreshPromise = (async () => {
            this.refreshing = true;
            this.refreshFailed = false;
            try {
                this.setupState = await fetchSetupState();
            } catch {
                // Preserve the last known section map so a transient refresh does
                // not replace useful state with an empty, misleading review.
                this.refreshFailed = true;
            } finally {
                this.refreshing = false;
                this.refreshPromise = null;
            }
        })();
        return this.refreshPromise;
    }

    indexOf(stepId: string): number {
        const i = this.steps.findIndex((s) => s.id === stepId);
        return i >= 0 ? i : 0;
    }

    goto(index: number): void {
        this.index = Math.max(0, Math.min(index, this.steps.length - 1));
    }

    gotoStep(stepId: string): void {
        this.goto(this.indexOf(stepId));
    }

    next(): void {
        this.goto(this.index + 1);
    }

    back(): void {
        this.goto(this.index - 1);
    }

    completeStep(): void {
        if (this.mode === 'rerun') this.gotoStep('review');
        else this.next();
    }

    skipStep(): void {
        this.completeStep();
    }

    leaveStep(): void {
        if (this.mode === 'rerun') this.gotoStep('review');
        else this.back();
    }

    get current(): WizardStep {
        return this.steps[this.index];
    }

    get isFirst(): boolean {
        return this.index === 0;
    }

    get isLast(): boolean {
        return this.index === this.steps.length - 1;
    }

    /** 1-based position within the flow, for "Step N of M" and the progress bar. */
    get position(): number {
        return this.index + 1;
    }

    get total(): number {
        return this.steps.length;
    }

    get progress(): number {
        return this.total > 1 ? this.index / (this.total - 1) : 1;
    }

    statusFor(section: SetupSectionId | null): SetupSectionStatus | null {
        if (!section || !this.setupState) return null;
        return this.setupState.sections.find((s) => s.id === section)?.status ?? null;
    }

    detailFor(section: SetupSectionId | null): string | null {
        if (!section || !this.setupState) return null;
        return this.setupState.sections.find((s) => s.id === section)?.detail ?? null;
    }
}

export const setupWizardStore = new SetupWizardStore();
