import { describe, expect, it } from 'vitest';
import detectionSettingsSource from '../components/settings/DetectionSettings.svelte?raw';
import setupModelSource from '../components/setup/ModelStep.svelte?raw';
import modelEvaluationSource from './ModelEvaluation.svelte?raw';
import modelManagerSource from './models/ModelManager.svelte?raw';

describe('model workflow polling lifecycle', () => {
    it('does not overlap slow model download status requests', () => {
        expect(modelManagerSource).toContain('if (pollingDownloads || document.hidden) return;');
        expect(modelManagerSource).toContain('pollingDownloads = false;');
    });

    it('does not overlap or background-poll model validation status', () => {
        expect(modelEvaluationSource).toContain('if (refreshInFlight) return;');
        expect(modelEvaluationSource).toContain('if (!document.hidden) void refresh();');
        expect(setupModelSource).toContain('if (pollInFlight || document.hidden) return;');
        expect(detectionSettingsSource).toContain('if (compatPollInFlight || document.hidden) return;');
    });
});
