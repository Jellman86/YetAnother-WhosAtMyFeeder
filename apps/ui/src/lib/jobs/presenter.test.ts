import { describe, expect, it } from 'vitest';
import type { AnalysisStatus } from '../api/maintenance';
import type { JobProgressItem } from '../stores/job_progress.svelte';
import type { JobPipelineKindRow } from './pipeline';
import { buildGlobalProgressSummary, presentActiveJob, presentPipelineKindRow } from './presenter';

function renderTemplate(template: string, values: Record<string, unknown> = {}): string {
    return template.replace(/\{(\w+)\}/g, (_, key) => String(values[key] ?? ''));
}

function t(_key: string, values?: Record<string, unknown>, fallback?: string): string {
    return renderTemplate(fallback ?? _key, values);
}

function makeJob(overrides: Partial<JobProgressItem> = {}): JobProgressItem {
    return {
        id: 'reclassify:evt-1',
        kind: 'reclassify',
        title: 'Analyze event',
        status: 'running',
        current: 3,
        total: 10,
        startedAt: 1_000,
        updatedAt: 121_000,
        source: 'sse',
        ...overrides
    };
}

function makeRow(overrides: Partial<JobPipelineKindRow> = {}): JobPipelineKindRow {
    return {
        kind: 'reclassify',
        queued: 12,
        queueDepthKnown: true,
        running: 2,
        stale: 0,
        completed: 0,
        failed: 0,
        queueUpdatedAt: 120_000,
        maxConcurrentConfigured: 4,
        maxConcurrentEffective: 2,
        mqttPressureLevel: null,
        throttledForMqttPressure: false,
        mqttInFlight: null,
        mqttInFlightCapacity: null,
        ...overrides
    };
}

describe('jobs presenter', () => {
    it('builds determinate progress and capacity labels for active reclassification work', () => {
        const presented = presentActiveJob(makeJob(), makeRow(), null, 125_000, t);

        expect(presented.activityLabel).toBe('Analyzing clips');
        expect(presented.progressLabel).toBe('3 / 10 frames');
        expect(presented.capacityLabel).toBe('2 of 4 worker slots busy');
        expect(presented.blockerLabel).toBeNull();
        expect(presented.detailLabel).toBeNull();
        expect(presented.determinate).toBe(true);
        expect(presented.percent).toBe(30);
    });

    it('marks MQTT-throttled work as waiting and indeterminate when total is unknown', () => {
        const presented = presentActiveJob(
            makeJob({ current: 0, total: 0 }),
            makeRow({
                running: 1,
                maxConcurrentConfigured: 4,
                maxConcurrentEffective: 2,
                throttledForMqttPressure: true,
                mqttPressureLevel: 'high',
                mqttInFlight: 9,
                mqttInFlightCapacity: 10
            }),
            null,
            125_000,
            t
        );

        expect(presented.activityLabel).toBe('Waiting for classifier slots');
        expect(presented.progressLabel).toBe('Working...');
        expect(presented.capacityLabel).toBe('1 of 2 worker slots busy');
        expect(presented.blockerLabel).toBe('MQTT pressure reduced background capacity');
        expect(presented.detailLabel).toBe('MQTT pressure reduced background capacity');
        expect(presented.determinate).toBe(false);
        expect(presented.percent).toBeNull();
    });

    it('surfaces circuit-open pause state for queue rows', () => {
        const analysisStatus: AnalysisStatus = {
            pending: 12,
            active: 0,
            circuit_open: true,
            failure_count: 4
        };

        const presented = presentPipelineKindRow(makeRow({ running: 0 }), analysisStatus, t);

        expect(presented.activityLabel).toBe('Paused by circuit breaker');
        expect(presented.blockerLabel).toBe('Recent failures paused reclassification work');
    });

    it('surfaces queue depth and free-capacity labels for throughput rows', () => {
        const analysisStatus: AnalysisStatus = {
            pending: 12,
            active: 2,
            circuit_open: false,
            pending_capacity: 200,
            pending_available: 188
        };

        const presented = presentPipelineKindRow(
            makeRow({ queued: null, queueDepthKnown: false }),
            analysisStatus,
            t
        );

        expect(presented.queueDepthLabel).toBe('Queue depth not reported');
        expect(presented.queueCapacityLabel).toBe('188 of 200 queue slots free');
    });

    it('does not leak reclassify circuit and queue telemetry into unrelated job rows', () => {
        const analysisStatus: AnalysisStatus = {
            pending: 12,
            active: 0,
            circuit_open: true,
            pending_capacity: 200,
            pending_available: 188
        };

        const presented = presentPipelineKindRow(
            makeRow({
                kind: 'backfill',
                queued: 0,
                queueDepthKnown: true,
                running: 1,
                maxConcurrentConfigured: null,
                maxConcurrentEffective: null
            }),
            analysisStatus,
            t
        );

        expect(presented.activityLabel).toBe('Processing work');
        expect(presented.blockerLabel).toBeNull();
        expect(presented.queueCapacityLabel).toBeNull();
    });

    it('marks stale jobs with explicit freshness labels', () => {
        const presented = presentActiveJob(
            makeJob({ status: 'stale', updatedAt: 0 }),
            makeRow(),
            null,
            301_000,
            t
        );

        expect(presented.freshnessLabel).toBe('No update for 5m 1s');
        expect(presented.detailLabel).toBe('No update for 5m 1s');
        expect(presented.isStale).toBe(true);
    });

    it('builds an indeterminate banner summary for mixed-unit jobs', () => {
        const summary = buildGlobalProgressSummary(
            [
                makeJob({ id: 'reclassify:evt-1', kind: 'reclassify', total: 10, current: 3 }),
                makeJob({ id: 'backfill:job-1', kind: 'backfill', total: 100, current: 20, title: 'Backfill' })
            ],
            new Map([
                ['reclassify', makeRow({ queued: 12, running: 1, maxConcurrentConfigured: 2 })],
                ['backfill', makeRow({ kind: 'backfill', queued: 0, running: 1, maxConcurrentConfigured: null, maxConcurrentEffective: null })]
            ]),
            {
                pending: 12,
                active: 1,
                circuit_open: false
            },
            125_000,
            t,
            (kind) => kind === 'reclassify' ? 'Reclassification' : 'Backfill'
        );

        expect(summary.headline).toBe('2 jobs running');
        expect(summary.subline).toBe('Reclassification analyzing clips');
        expect(summary.determinate).toBe(false);
        expect(summary.progressLabel).toBe('Multiple jobs in progress');
    });

    it('chooses the highest-pressure job family for the banner summary, not just the newest update', () => {
        const summary = buildGlobalProgressSummary(
            [
                makeJob({ id: 'backfill:job-1', kind: 'backfill', total: 100, current: 20, title: 'Backfill', updatedAt: 130_000 }),
                makeJob({ id: 'reclassify:evt-1', kind: 'reclassify', total: 10, current: 3, updatedAt: 120_000 })
            ],
            new Map([
                ['reclassify', makeRow({ queued: 12, running: 1, maxConcurrentConfigured: 2 })],
                ['backfill', makeRow({ kind: 'backfill', queued: 0, running: 1, maxConcurrentConfigured: null, maxConcurrentEffective: null })]
            ]),
            {
                pending: 12,
                active: 1,
                circuit_open: false
            },
            130_000,
            t,
            (kind) => kind === 'reclassify' ? 'Reclassification' : 'Backfill'
        );

        expect(summary.subline).toBe('Reclassification analyzing clips');
    });

    it('builds a determinate banner summary when active jobs share a unit', () => {
        const summary = buildGlobalProgressSummary(
            [
                makeJob({ id: 'reclassify:evt-1', current: 3, total: 10 }),
                makeJob({ id: 'reclassify:evt-2', current: 5, total: 10 })
            ],
            new Map([['reclassify', makeRow({ queued: 4, running: 2, maxConcurrentConfigured: 2 })]]),
            {
                pending: 4,
                active: 2,
                circuit_open: false
            },
            125_000,
            t,
            () => 'Reclassification'
        );

        expect(summary.determinate).toBe(true);
        expect(summary.percent).toBe(40);
        expect(summary.headline).toBe('2 jobs running');
        expect(summary.progressLabel).toBe('8 / 20 frames');
    });
});
