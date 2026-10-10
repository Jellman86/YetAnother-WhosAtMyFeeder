import type { ModelEvalModelSummary } from '../api/model_eval';

export interface ModelEvalScores {
    top1: number | null;
    top3: number | null;
    core: number | null;
    region: number | null;
    /** "116 of 141", or null when the run does not know which birds the model can name. */
    canName: string | null;
}

/**
 * Compatibility-only runs (the Detection Settings check and the setup wizard) mark
 * every row with this provider. Their accuracy fields are zero placeholders, so the
 * marker, not a zero score, is what says accuracy was never measured.
 */
const COMPATIBILITY_SWEEP_PROVIDER = 'validation_sweep';

function isCompatibilityOnlyRow(model: ModelEvalModelSummary): boolean {
    return model.requested_provider === COMPATIBILITY_SWEEP_PROVIDER;
}

export function isCompatibilityOnlyRun(models: ModelEvalModelSummary[] | undefined): boolean {
    return Boolean(models?.length) && (models ?? []).every(isCompatibilityOnlyRow);
}

/**
 * The accuracy a model should be compared on: the test birds it can name.
 *
 * A regional model has no output for birds outside its region, so counting them as misses
 * scored the European FocalNet model 52.8% when it got 83.0% of the European birds right.
 * Runs that do not know a model's vocabulary (older runs, or a model the species catalogue
 * does not know) show the figures over every test bird, as before. A compatibility-only row
 * has no accuracy at all.
 */
export function modelEvalScores(model: ModelEvalModelSummary): ModelEvalScores {
    if (isCompatibilityOnlyRow(model)) {
        return { top1: null, top3: null, core: null, region: null, canName: null };
    }
    if (!model.vocabulary_known) {
        return {
            top1: model.top1_accuracy,
            top3: model.top3_accuracy,
            core: model.shared_core_top1,
            region: model.regional_top1,
            canName: null,
        };
    }
    const total = model.panel_species ?? 0;
    const outside = model.species_outside_vocabulary ?? 0;
    return {
        top1: model.top1_accuracy_in_vocabulary ?? null,
        top3: model.top3_accuracy_in_vocabulary ?? null,
        core: model.shared_core_top1_in_vocabulary ?? null,
        region: model.regional_top1_in_vocabulary ?? null,
        canName: total ? `${total - outside} of ${total}` : null,
    };
}
