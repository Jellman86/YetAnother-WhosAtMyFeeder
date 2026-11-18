import { describe, expect, it, vi } from 'vitest';
import type { BackendDiagnosticEvent, DiagnosticsWorkspacePayload } from '../api/diagnostics';
import { asGuarded } from '../test-support/guarded';
import { createIncidentWorkspaceStore } from './incident_workspace.svelte';

function entry(overrides: Partial<BackendDiagnosticEvent> = {}): BackendDiagnosticEvent {
    return {
        id: 'diag:1:1',
        source: 'event_pipeline',
        component: 'event_processor',
        reason_code: 'drop_classify_snapshot_timeout',
        severity: 'error',
        message: 'Dropped event due to classify_snapshot_timeout',
        timestamp: '2026-11-18T07:00:00.123456+00:00',
        last_seen: '2026-11-18T07:00:00.123456+00:00',
        count: 1,
        dismissed: false,
        ...overrides
    };
}

function workspace(events: BackendDiagnosticEvent[], health: Record<string, unknown> = {}): DiagnosticsWorkspacePayload {
    return {
        health,
        workspace_schema_version: 'test',
        classifier: {},
        taxonomy_repair: {},
        maintenance_coordinator: {},
        focused_diagnostics: {},
        startup_warnings: [],
        backend_diagnostics: {
            captured_at: '2026-11-18T07:05:00Z',
            capacity: 500,
            total_events: events.length,
            filtered_events: events.length,
            returned_events: events.length,
            severity_counts: {},
            component_counts: {},
            events
        }
    } as DiagnosticsWorkspacePayload;
}

describe('dismissed Health items', () => {
    it('hides an incident once every entry it is built from is dismissed, and keeps it for Show dismissed', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([entry({ dismissed: true })]));

        expect(store.currentIssues).toHaveLength(0);
        expect(store.recentIncidents).toHaveLength(0);
        expect(store.dismissedIncidents.map((incident) => [incident.primaryReasonCode, incident.dismissed]))
            .toEqual([['drop_classify_snapshot_timeout', true]]);
    });

    it('shows the incident again when the backend says a newer occurrence ended the dismissal', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([entry({ dismissed: true })]));
        store.ingestWorkspacePayload(workspace([entry({ dismissed: false, count: 2, last_seen: '2026-11-18T07:10:00Z', timestamp: '2026-11-18T07:10:00Z' })]));

        expect(store.currentIssues.map((incident) => incident.dismissed)).toEqual([false]);
        expect(store.dismissedIncidents).toHaveLength(0);
    });

    it('keeps an incident while any entry it is built from is still undismissed', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([
            entry({ id: 'diag:1:1', correlation_key: 'camera:patio', dismissed: true }),
            entry({ id: 'diag:1:2', correlation_key: 'camera:patio', reason_code: 'stage_timeout', dismissed: false })
        ]));

        expect(store.currentIssues).toHaveLength(1);
        expect(store.dismissedIncidents).toHaveLength(0);
    });

    it('never hides an incident a live check still shows open, so dismissing cannot make a failure look fixed', () => {
        const store = createIncidentWorkspaceStore();
        const breaker = entry({ component: 'video_classifier', reason_code: 'circuit_open', severity: 'warning', dismissed: true });
        store.ingestWorkspacePayload(workspace([breaker], { video_classifier: { circuit_open: true } }));

        expect(store.currentIssues.map((incident) => [incident.live, incident.dismissed])).toEqual([[true, false]]);
        expect(store.dismissedIncidents).toHaveLength(0);
    });

    it('names the entries and the occurrence the owner saw when an incident is dismissed', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([
            entry({ id: 'diag:1:1', correlation_key: 'camera:patio' }),
            entry({ id: 'diag:1:2', correlation_key: 'camera:patio', reason_code: 'stage_timeout', last_seen: '2026-11-18T07:02:00Z' })
        ]));

        expect(store.dismissalEntries(store.currentIssues[0])).toEqual([
            { id: 'diag:1:1', last_seen: '2026-11-18T07:00:00.123456+00:00' },
            { id: 'diag:1:2', last_seen: '2026-11-18T07:02:00Z' }
        ]);
    });

    it('exports every incident, the dismissed ones marked as dismissed', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([
            entry({ id: 'diag:1:1', dismissed: true }),
            entry({ id: 'diag:1:2', component: 'notification_dispatcher', reason_code: 'send_failed', dismissed: false })
        ]));

        const exported = store.exportIncidents();
        expect(exported.current.map((incident) => [incident.primaryReasonCode, incident.dismissed]).sort())
            .toEqual([['drop_classify_snapshot_timeout', true], ['send_failed', false]]);
        expect(exported.recent).toEqual([]);
    });

    it('dismisses and restores through the server, then reads the workspace again', async () => {
        const fetchWorkspace = vi.fn(() => asGuarded(Promise.resolve(workspace([entry({ dismissed: true })]))));
        const dismiss = vi.fn(() => Promise.resolve({ dismissed: [], missing: [] }));
        const restore = vi.fn(() => Promise.resolve({ restored: ['diag:1:1'] }));
        const store = createIncidentWorkspaceStore(fetchWorkspace, { dismiss, restore });

        await store.dismissRemote([{ id: 'diag:1:1', last_seen: '2026-11-18T07:00:00Z' }]);
        expect(dismiss).toHaveBeenCalledWith([{ id: 'diag:1:1', last_seen: '2026-11-18T07:00:00Z' }]);
        expect(store.dismissedIncidents).toHaveLength(1);

        await store.restoreRemote(['diag:1:1']);
        expect(restore).toHaveBeenCalledWith(['diag:1:1']);
        expect(fetchWorkspace).toHaveBeenCalledTimes(2);
    });
});
