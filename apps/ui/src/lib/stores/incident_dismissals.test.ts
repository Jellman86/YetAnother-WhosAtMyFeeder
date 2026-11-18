import { describe, expect, it, vi } from 'vitest';
import type { BackendDiagnosticEvent, DiagnosticsWorkspacePayload } from '../api/diagnostics';
import { asGuarded } from '../test-support/guarded';
import { createIncidentWorkspaceStore, dismissOutcome } from './incident_workspace.svelte';

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

    it('names the entries and how many occurrences the owner saw when an incident is dismissed', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([
            entry({ id: 'diag:1:1', correlation_key: 'camera:patio' }),
            entry({ id: 'diag:1:2', correlation_key: 'camera:patio', reason_code: 'stage_timeout', count: 4 })
        ]));

        expect(store.dismissalEntries(store.currentIssues[0])).toEqual([
            { id: 'diag:1:1', count: 1 },
            { id: 'diag:1:2', count: 4 }
        ]);
    });

    it('treats a stateful incident whose live check has no reading as live, so it cannot be dismissed', () => {
        const store = createIncidentWorkspaceStore();
        // The finder's state is not in this reading at all: unmeasured, so never hidden.
        const finder = entry({ component: 'bird_finder', reason_code: 'rfdetr_cpu_fallback', severity: 'warning', dismissed: true });
        store.ingestWorkspacePayload(workspace([finder], { ml: {} }));

        expect(store.currentIssues.map((incident) => [incident.live, incident.dismissed])).toEqual([[true, false]]);
        expect(store.dismissedIncidents).toHaveLength(0);
    });

    it('lets a stateful incident be dismissed once its live check has measured it closed', () => {
        const store = createIncidentWorkspaceStore();
        const finder = entry({ component: 'bird_finder', reason_code: 'rfdetr_cpu_fallback', severity: 'warning', dismissed: true });
        store.ingestWorkspacePayload(workspace([finder], { ml: { bird_finder: { active: false } } }));

        expect(store.dismissedIncidents.map((incident) => [incident.live, incident.dismissed])).toEqual([[false, true]]);
    });

    it('says whether an item is still listed after a read', () => {
        const store = createIncidentWorkspaceStore();
        store.ingestWorkspacePayload(workspace([entry({ id: 'diag:1:1' }), entry({ id: 'diag:1:2', reason_code: 'stage_failure', dismissed: true })]));

        expect(store.isListed('entry:diag:1:1')).toBe(true);
        expect(store.isListed('entry:diag:1:2')).toBe(false);
        expect(store.isListed('incident:event_processor:drop_classify_snapshot_timeout')).toBe(true);
        expect(store.isListed('incident:event_processor:stage_failure')).toBe(false);
        expect(store.isListed('entry:diag:gone')).toBe(false);
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

        const result = await store.dismissRemote([{ id: 'diag:1:1', count: 1 }]);
        expect(dismiss).toHaveBeenCalledWith([{ id: 'diag:1:1', count: 1 }]);
        expect(result).toEqual({ dismissed: [], missing: [] });
        expect(store.dismissedIncidents).toHaveLength(1);

        await store.restoreRemote(['diag:1:1']);
        expect(restore).toHaveBeenCalledWith(['diag:1:1']);
        expect(fetchWorkspace).toHaveBeenCalledTimes(2);
    });
});

describe('what a dismissal did', () => {
    const covered = { id: 'diag:1:1', component: 'event_processor', reason_code: 'stage_timeout', dismissed_count: 1, dismissed_at: '2026-11-18T07:05:00Z' };

    it('is a dismissal only when the server hid it and the next read no longer lists it', () => {
        expect(dismissOutcome({ dismissed: [covered], missing: [] }, false)).toBe('dismissed');
    });

    it('says it happened again when a newer occurrence keeps it listed', () => {
        // The page saw one occurrence; a second arrived before the click, so the server hid only the first.
        expect(dismissOutcome({ dismissed: [covered], missing: [] }, true)).toBe('happened_again');
    });

    it('says it was already cleared when the server no longer has it', () => {
        // A clear in another tab, the history's limit, or a restart emptied it before the click.
        expect(dismissOutcome({ dismissed: [], missing: ['diag:1:1'] }, false)).toBe('already_cleared');
    });
});
