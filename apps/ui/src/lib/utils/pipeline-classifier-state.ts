import type { ClassifierStatus } from '../api/classifier';
import type { ModelReadiness } from '../settings/model-readiness';

/**
 * The classifier step of the About pipeline, read from `/api/classifier/status`.
 *
 * In the default subprocess mode the model lives in worker processes, so the
 * status has no top-level `loaded` flag. Its absence is not evidence of a
 * fault: the answer then comes from inference health and the model id, and
 * with neither the state is unknown rather than "not loaded".
 */
export type PipelineClassifierState = 'loaded' | 'standby' | 'missing' | 'check' | 'unknown';

export function pipelineClassifierState(status: ClassifierStatus | null): PipelineClassifierState {
    if (!status) return 'unknown';
    // The same reading the status sentence uses: files that are not here cannot be "not loaded yet".
    if (status.active_model_installed === false) return 'missing';

    const health = status.inference_health?.status;
    if (health === 'degraded' || health === 'unhealthy') return 'check';
    if (typeof status.error === 'string' && status.error.trim()) return 'check';

    // Workers load the model on first use, so an in-process flag of false says
    // nothing about them; only an in-process install's flag is the whole story.
    if (status.image_execution_mode !== 'subprocess' && typeof status.loaded === 'boolean') {
        return status.loaded ? 'loaded' : 'check';
    }
    if (status.loaded === true) return 'loaded';

    const modelId = status.effective_model_id ?? status.active_model_id;
    if (!modelId || health !== 'ok') return 'unknown';
    // Loaded and standing by each need evidence. An in-app model with no `loaded` reading is being
    // (re)loaded, and that is not a state this step can claim.
    const inApp = status.runtime_source === 'in_process' || status.runtime_source === 'in_process_fallback'
        || (status.image_execution_mode === 'in_process' && status.runtime_source !== 'worker' && status.runtime_source !== 'planned');
    if (inApp) return 'unknown';
    return status.runtime_source === 'planned' ? 'standby' : 'loaded';
}

/**
 * The step's state in the readiness vocabulary Settings, the wizard and Garden use, so About says
 * "Running", "Ready" or "Needs a download" in the same words. A health check and an unknown are
 * the pipeline's own states and have no readiness word.
 */
export function pipelineReadiness(state: PipelineClassifierState): ModelReadiness | null {
    if (state === 'loaded') return 'running';
    if (state === 'standby') return 'ready';
    if (state === 'missing') return 'missing';
    return null;
}
