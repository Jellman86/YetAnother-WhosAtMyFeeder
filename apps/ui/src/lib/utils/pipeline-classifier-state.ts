import type { ClassifierStatus } from '../api/classifier';

/**
 * The classifier step of the About pipeline, read from `/api/classifier/status`.
 *
 * In the default subprocess mode the model lives in worker processes, so the
 * status has no top-level `loaded` flag. Its absence is not evidence of a
 * fault: the answer then comes from inference health and the model id, and
 * with neither the state is unknown rather than "not loaded".
 */
export type PipelineClassifierState = 'loaded' | 'standby' | 'check' | 'unknown';

export function pipelineClassifierState(status: ClassifierStatus | null): PipelineClassifierState {
    if (!status) return 'unknown';

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
    return status.runtime_source === 'planned' ? 'standby' : 'loaded';
}
