import type { ClassifierStatus } from '../api/classifier';

export function classifierRuntimeState(status: ClassifierStatus | null, savedMode: string): {
    executionMode: string;
    restartRecommended: boolean;
    recovering: boolean;
} {
    const reportedMode = status?.image_execution_mode;
    return {
        executionMode: reportedMode === 'subprocess' || reportedMode === 'in_process' ? reportedMode : savedMode,
        restartRecommended: status?.native_runtime_quarantine?.restart_recommended === true,
        recovering: status?.native_runtime_quarantine?.status === 'recovering',
    };
}
