import { describe, expect, it } from 'vitest';

import {
    eventPipelineVerdict,
    expectedDropCount,
    expectedDropReasons,
    faultDropCount,
    faultDropReasons,
    hasExpectedDrops
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
