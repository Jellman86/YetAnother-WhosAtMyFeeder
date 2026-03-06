import { beforeEach, describe, expect, it, vi } from 'vitest';
import { jobDiagnosticsStore } from './job_diagnostics.svelte';

describe('jobDiagnosticsStore', () => {
    beforeEach(() => {
        jobDiagnosticsStore.clear();
        vi.useFakeTimers();
        vi.setSystemTime(new Date('2026-03-06T12:00:00.000Z'));
    });

    it('deduplicates repeated errors into one grouped record', () => {
        jobDiagnosticsStore.recordError({
            source: 'sse',
            component: 'event_pipeline',
            stage: 'classify_snapshot',
            reasonCode: 'stage_timeout',
            message: 'Stage timed out',
            severity: 'error',
            eventId: 'evt-1'
        });
        jobDiagnosticsStore.recordError({
            source: 'sse',
            component: 'event_pipeline',
            stage: 'classify_snapshot',
            reasonCode: 'stage_timeout',
            message: 'Stage timed out',
            severity: 'error',
            eventId: 'evt-2'
        });

        expect(jobDiagnosticsStore.groups.length).toBe(1);
        expect(jobDiagnosticsStore.groups[0].count).toBe(2);
        expect(jobDiagnosticsStore.groups[0].sampleEventIds).toEqual(['evt-2', 'evt-1']);
    });

    it('ingests health payload and records grouped health diagnostics', () => {
        jobDiagnosticsStore.ingestHealth({
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: {
                pressure_level: 'critical',
                in_flight: 200,
                in_flight_capacity: 200
            },
            event_pipeline: {
                critical_failures: 2,
                stage_timeouts: {
                    classify_snapshot: 4
                },
                stage_failures: {}
            },
            notification_dispatcher: {
                dropped_jobs: 3
            },
            db_pool: {
                acquire_wait_max_ms: 9000
            },
            startup_warnings: [
                { phase: 'mqtt_service_task_start', error: 'connection retrying' }
            ]
        });

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(1);
        const timeoutGroup = jobDiagnosticsStore.groups.find(
            (group) =>
                group.component === 'event_pipeline'
                && group.stage === 'classify_snapshot'
                && group.reasonCode === 'stage_timeout'
        );
        expect(timeoutGroup).toBeTruthy();
        expect(timeoutGroup?.count).toBe(1);
        expect(jobDiagnosticsStore.groups.some((group) => group.component === 'mqtt')).toBe(true);
        expect(jobDiagnosticsStore.groups.some((group) => group.component === 'db_pool')).toBe(true);
    });

    it('deduplicates identical consecutive health snapshots and exports JSON', () => {
        const payload = {
            status: 'degraded',
            startup_instance_id: 'abc123',
            mqtt: { pressure_level: 'high' },
            event_pipeline: { critical_failures: 1, stage_timeouts: {}, stage_failures: {} },
            notification_dispatcher: { dropped_jobs: 0 },
            db_pool: { acquire_wait_max_ms: 0 },
            startup_warnings: []
        };
        jobDiagnosticsStore.ingestHealth(payload);
        jobDiagnosticsStore.ingestHealth(payload);

        expect(jobDiagnosticsStore.healthSnapshots.length).toBe(1);

        const exported = jobDiagnosticsStore.exportJson();
        const summary = exported.summary as Record<string, unknown>;
        const groups = exported.error_groups as Array<Record<string, unknown>>;
        const snapshots = exported.health_snapshots as Array<Record<string, unknown>>;

        expect(typeof exported.generated_at).toBe('string');
        expect(Number(summary.error_groups)).toBeGreaterThan(0);
        expect(groups.length).toBeGreaterThan(0);
        expect(snapshots.length).toBe(1);
        expect(snapshots[0].status).toBe('degraded');
    });
});
