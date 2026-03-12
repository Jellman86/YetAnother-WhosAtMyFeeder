import { describe, expect, it } from 'vitest';
import { createIncidentWorkspaceStore } from './incident_workspace.svelte';

describe('incidentWorkspaceStore', () => {
    it('correlates backend diagnostics and failed jobs into one current incident', () => {
        const store = createIncidentWorkspaceStore();

        store.ingestBackendDiagnostics([
            {
                id: 'diag-1',
                component: 'classifier_supervisor',
                reason_code: 'background_image_worker_unavailable',
                severity: 'error',
                message: 'Background workers unavailable',
                timestamp: '2026-03-12T10:00:00Z',
                job_id: 'job-1'
            }
        ]);
        store.ingestJobState({
            id: 'job-1',
            kind: 'backfill_detection',
            status: 'failed',
            message: 'classification failed'
        });

        expect(store.currentIssues).toHaveLength(1);
        expect(store.currentIssues[0].affected_area).toBe('backfill');
        expect(store.currentIssues[0].evidenceRefs).toContain('diag-1');
        expect(store.currentIssues[0].evidenceRefs).toContain('job:job-1');
    });

    it('moves resolved incidents out of current issues and keeps them in recent history', () => {
        const store = createIncidentWorkspaceStore();

        store.ingestBackendDiagnostics([
            {
                id: 'diag-2',
                component: 'classifier_supervisor',
                reason_code: 'background_image_worker_unavailable',
                severity: 'error',
                message: 'Background workers unavailable',
                timestamp: '2026-03-12T10:00:00Z',
                job_id: 'job-2'
            }
        ]);
        store.ingestJobState({
            id: 'job-2',
            kind: 'backfill_detection',
            status: 'failed'
        });
        store.ingestJobState({
            id: 'job-2',
            kind: 'backfill_detection',
            status: 'completed'
        });

        expect(store.currentIssues).toHaveLength(0);
        expect(store.recentIncidents).toHaveLength(1);
        expect(store.recentIncidents[0].status).toBe('resolved');
        expect(store.recentIncidents[0].evidenceRefs).toContain('diag-2');
    });
});
