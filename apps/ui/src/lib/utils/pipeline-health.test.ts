import { describe, expect, it } from 'vitest';

import {
    eventPipelineVerdict,
    expectedDropCount,
    expectedDropReasons,
    faultDiagnostics,
    faultDropCount,
    faultDropReasons,
    hasExpectedDrops,
    recentFilteredDetections
} from './pipeline-health';

describe('event pipeline verdict', () => {
    it('stays healthy when every drop was expected filtering', () => {
        // The live instance this was found on: 12 low-confidence rejections and
        // nothing else, reported healthy by the backend.
        const pipeline = {
            status: 'ok',
            critical_failure_active: false,
            critical_failures: 0,
            dropped_events: 12,
            expected_drops: 12,
            fault_drops: 0,
            expected_drop_reasons: { filter_low_confidence: 12 },
            fault_drop_reasons: {}
        };
        expect(eventPipelineVerdict(pipeline, 'ok')).toBe('ok');
    });

    it('degrades when a drop was caused by a fault', () => {
        const pipeline = {
            status: 'ok',
            dropped_events: 5,
            expected_drops: 4,
            fault_drops: 1,
            fault_drop_reasons: { classifier_empty_results: 1 }
        };
        expect(eventPipelineVerdict(pipeline, 'ok')).toBe('degraded');
    });

    it('reports critical while a critical failure is still active', () => {
        expect(
            eventPipelineVerdict({ status: 'degraded', critical_failure_active: true, fault_drops: 0 }, 'ok')
        ).toBe('critical');
    });

    it('repeats the status the backend reported rather than inventing one', () => {
        expect(eventPipelineVerdict({ status: 'degraded', fault_drops: 0 }, 'ok')).toBe('degraded');
    });

    it('falls back only when the backend sent no status', () => {
        expect(eventPipelineVerdict({}, 'unknown')).toBe('unknown');
        expect(eventPipelineVerdict(null, 'unknown')).toBe('unknown');
        expect(eventPipelineVerdict({ status: '   ' }, 'unknown')).toBe('unknown');
    });

    it('ignores an older backend that does not send the split counters', () => {
        expect(eventPipelineVerdict({ status: 'ok', dropped_events: 12 }, 'ok')).toBe('ok');
    });
});

describe('drop counts', () => {
    const pipeline = {
        expected_drops: 13,
        fault_drops: 2,
        expected_drop_reasons: { filter_low_confidence: 12, filter_blocked_label: 1 },
        fault_drop_reasons: { classify_snapshot_timeout: 2 }
    };

    it('separates expected filtering from faults', () => {
        expect(expectedDropCount(pipeline)).toBe(13);
        expect(faultDropCount(pipeline)).toBe(2);
        expect(hasExpectedDrops(pipeline)).toBe(true);
    });

    it('orders reasons by how often they happened', () => {
        expect(expectedDropReasons(pipeline)).toEqual([
            { reason: 'filter_low_confidence', count: 12 },
            { reason: 'filter_blocked_label', count: 1 }
        ]);
        expect(faultDropReasons(pipeline)).toEqual([{ reason: 'classify_snapshot_timeout', count: 2 }]);
    });

    it('treats missing, zero and unusable values as nothing to report', () => {
        expect(expectedDropCount({})).toBe(0);
        expect(expectedDropCount(null)).toBe(0);
        expect(faultDropCount({ fault_drops: 'lots' })).toBe(0);
        expect(faultDropCount({ fault_drops: -3 })).toBe(0);
        expect(hasExpectedDrops({ expected_drops: 0 })).toBe(false);
        expect(expectedDropReasons({ expected_drop_reasons: [] })).toEqual([]);
        expect(expectedDropReasons({ expected_drop_reasons: { filter_low_confidence: 0 } })).toEqual([]);
    });
});

describe('recent filtered detections', () => {
    const outcomes = [
        { event_id: 'a', outcome: 'completed', duration_ms: 3 },
        { event_id: 'b', outcome: 'dropped', reason: 'filter_low_confidence', label: 'Catharus fuscescens', score: 0.1115, timestamp: '2026-08-15T05:53:06Z' },
        { event_id: 'c', outcome: 'dropped', reason: 'classifier_empty_results' },
        { event_id: 'd', outcome: 'dropped', reason: 'filter_low_confidence', label: 'Oryctolagus cuniculus', score: 0.2074, timestamp: '2026-08-15T06:15:57Z' }
    ];

    it('lists what the filter rejected, newest first', () => {
        expect(recentFilteredDetections({ recent_outcomes: outcomes })).toEqual([
            { eventId: 'd', reason: 'filter_low_confidence', label: 'Oryctolagus cuniculus', score: 0.2074, timestamp: '2026-08-15T06:15:57Z' },
            { eventId: 'b', reason: 'filter_low_confidence', label: 'Catharus fuscescens', score: 0.1115, timestamp: '2026-08-15T05:53:06Z' }
        ]);
    });

    it('leaves fault drops to the pipeline card', () => {
        const reasons = recentFilteredDetections({ recent_outcomes: outcomes }).map(entry => entry.reason);
        expect(reasons).not.toContain('classifier_empty_results');
    });

    it('honours the limit and tolerates unusable payloads', () => {
        expect(recentFilteredDetections({ recent_outcomes: outcomes }, 1)).toHaveLength(1);
        expect(recentFilteredDetections({ recent_outcomes: 'nope' })).toEqual([]);
        expect(recentFilteredDetections({})).toEqual([]);
        expect(recentFilteredDetections(null)).toEqual([]);
    });

    it('skips rows with no event id or missing label', () => {
        const entries = recentFilteredDetections({
            recent_outcomes: [
                { outcome: 'dropped', reason: 'filter_low_confidence', label: 'No id' },
                { event_id: 'e', outcome: 'dropped', reason: 'filter_blocked_label' }
            ]
        });
        expect(entries).toEqual([
            { eventId: 'e', reason: 'filter_blocked_label', label: null, score: null, timestamp: null }
        ]);
    });
});

describe('backend diagnostics list', () => {
    it('keeps warnings and errors and drops expected filtering noise', () => {
        const events = [
            { id: '1', severity: 'info', reason_code: 'drop_filter_low_confidence' },
            { id: '2', severity: 'warning', reason_code: 'drop_classifier_empty_results' },
            { id: '3', severity: 'error', reason_code: 'drop_save_and_notify_failed' },
            { id: '4', severity: 'INFO', reason_code: 'drop_filter_blocked_label' }
        ];
        expect(faultDiagnostics(events).map(event => event.id)).toEqual(['2', '3']);
    });

    it('treats a missing severity as a warning rather than hiding it', () => {
        const withoutSeverity: Array<{ id: string; severity?: string }> = [{ id: '1' }];
        expect(faultDiagnostics(withoutSeverity)).toHaveLength(1);
        expect(faultDiagnostics(null)).toEqual([]);
    });
});
