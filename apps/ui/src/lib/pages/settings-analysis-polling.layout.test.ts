import { describe, expect, it } from 'vitest';
import settingsSource from './Settings.svelte?raw';

describe('Settings analysis status lifecycle', () => {
    it('consumes the application-owned queue status instead of starting another poller', () => {
        expect(settingsSource).toContain("import { analysisQueueStatusStore } from '../stores/analysis_queue_status.svelte';");
        expect(settingsSource).toContain('const status = analysisQueueStatusStore.analysisStatus;');
        expect(settingsSource).toContain('await analysisQueueStatusStore.refresh();');
        expect(settingsSource).not.toContain('fetchAnalysisStatus,');
        expect(settingsSource).not.toContain('analysisPollInterval');
        expect(settingsSource).not.toContain('startAnalysisPolling');
    });

    it('prevents slow settings status requests from overlapping', () => {
        expect(settingsSource).toContain('if (taxonomyStatusLoading) return;');
        expect(settingsSource).toContain('if (backfillStatusLoading) return;');
        expect(settingsSource).toContain('if (!document.hidden) void loadTaxonomyStatus();');
        expect(settingsSource).toContain('if (!document.hidden) void loadBackfillStatus();');
        expect(settingsSource).toContain('taxonomyStatusLoading = false;');
        expect(settingsSource).toContain('backfillStatusLoading = false;');
    });
});
