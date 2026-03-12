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

    it('builds an issue-ready draft with environment and incident summary', () => {
        const store = createIncidentWorkspaceStore();

        store.ingestWorkspacePayload({
            workspace_schema_version: '2026-03-12.owner-incident-workspace.v1',
            backend_diagnostics: {
                captured_at: '2026-03-12T10:05:00Z',
                capacity: 500,
                total_events: 1,
                filtered_events: 1,
                returned_events: 1,
                severity_counts: { error: 1 },
                component_counts: { classifier_supervisor: 1 },
                events: [
                    {
                        id: 'diag-3',
                        component: 'classifier_supervisor',
                        reason_code: 'background_image_worker_unavailable',
                        severity: 'error',
                        message: 'Background workers unavailable',
                        timestamp: '2026-03-12T10:00:00Z',
                        job_id: 'job-3'
                    }
                ]
            },
            health: {
                status: 'degraded',
                service: 'ya-wamf-backend',
                version: '2.8.3-dev'
            },
            startup_warnings: []
        });
        store.ingestJobState({ id: 'job-3', kind: 'backfill_detection', status: 'failed' });

        const draft = store.buildIssueDraft(store.currentIssues[0], {
            bundleLabel: 'backfill failure',
            bundleSchemaVersion: 2
        });

        expect(draft.title).toMatch(/Background workers unavailable/i);
        expect(draft.body).toContain('Environment');
        expect(draft.body).toContain('Incident Summary');
        expect(draft.body).toContain('backfill');
        expect(draft.bundleSchemaVersion).toBe(2);
    });

    it('surfaces local diagnostic groups as current incidents when backend evidence is absent', () => {
        const store = createIncidentWorkspaceStore();

        store.ingestLocalDiagnosticGroups([
            {
                fingerprint: 'runtime|frontend|-|uncaught_exception',
                component: 'frontend',
                reasonCode: 'uncaught_exception',
                severity: 'error',
                message: 'Owner page crashed',
                firstSeen: Date.parse('2026-03-12T10:00:00Z'),
                lastSeen: Date.parse('2026-03-12T10:01:00Z')
            }
        ]);

        expect(store.currentIssues).toHaveLength(1);
        expect(store.currentIssues[0].affected_area).toBe('frontend');
        expect(store.currentIssues[0].evidenceRefs).toContain('local:runtime|frontend|-|uncaught_exception');
    });
});
