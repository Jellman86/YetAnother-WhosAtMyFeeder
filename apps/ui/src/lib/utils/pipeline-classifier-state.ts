import type { ClassifierStatus } from '../api/classifier';
import { classifierReadiness, readinessTone, type ActivityPhase, type ModelReadiness } from '../settings/model-readiness';

/**
 * The classifier step of the About pipeline, read from `/api/classifier/status`.
 *
 * The step states the model's readiness by the rule Settings, the wizard and Garden use, so About
 * cannot disagree with them. Inference health is a different reading (did recent inferences
 * succeed) and is reported beside it, never folded into the model's state: a model can be running
 * with failing inferences, or running with no health data at all.
 */
export interface PipelineClassifierStep {
    readiness: ModelReadiness;
    /** Reported only when the classifier says inference is in trouble; null when it is fine or unreported. */
    health: 'degraded' | 'unhealthy' | null;
    tone: 'ok' | 'off' | 'unknown';
}

export function pipelineClassifierStep(status: ClassifierStatus | null, phase: ActivityPhase | null = null): PipelineClassifierStep {
    const readiness = classifierReadiness(status, phase);
    const reported = status?.inference_health?.status;
    const health = reported === 'degraded' || reported === 'unhealthy' ? reported : null;
    const measured = readinessTone(readiness);
    // The pipeline's lit dot means "working": a model with failing inferences is not lit.
    const tone = measured === 'ok' && health === null ? 'ok' : measured === 'neutral' ? 'unknown' : 'off';
    return { readiness, health, tone };
}
