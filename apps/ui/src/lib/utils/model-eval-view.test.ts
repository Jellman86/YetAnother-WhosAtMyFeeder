import { describe, expect, it } from 'vitest';
import { ApiRequestError } from '../api/core';
import type { DeviceMatrix, ModelEvalModelSummary } from '../api/model_eval';
import {
    checkRowProblem,
    downloadStatement,
    evaluationFiles,
    evaluationProblem,
    evaluationProgress,
    evaluationStarted,
    historyPane,
    missingModelDownload,
    providerCheck,
    skipReason,
    stopCause,
    warningCopy
} from './model-eval-view';

describe('the past evaluations pane', () => {
    it('is loading until the first read lands, and never empty before then', () => {
        expect(historyPane({ loaded: false, failed: false, count: 0 })).toBe('loading');
    });

    it('says the read failed instead of claiming there are no evaluations', () => {
        expect(historyPane({ loaded: false, failed: true, count: 0 })).toBe('failed');
    });

    it('is empty only once a read measured zero', () => {
        expect(historyPane({ loaded: true, failed: false, count: 0 })).toBe('empty');
    });

    it('keeps an earlier list on screen when a later refresh fails', () => {
        expect(historyPane({ loaded: true, failed: true, count: 3 })).toBe('list');
        expect(historyPane({ loaded: true, failed: false, count: 3 })).toBe('list');
    });
});

describe('when an evaluation started', () => {
    it('reads the recorded start time', () => {
        expect(evaluationStarted({ run_id: '20261010-163945', started_at: '2026-10-10T16:40:00Z' })?.toISOString())
            .toBe('2026-10-10T16:40:00.000Z');
    });

    it('falls back to the time in the identifier, which is UTC', () => {
        expect(evaluationStarted({ run_id: '20261010-163945' })?.toISOString()).toBe('2026-10-10T16:39:45.000Z');
    });

    it('is unknown for an identifier that carries no time', () => {
        expect(evaluationStarted({ run_id: 'run-1' })).toBeNull();
        expect(evaluationStarted({ run_id: '20269999-999999', started_at: 'nonsense' })).toBeNull();
    });
});

describe('progress of a running evaluation', () => {
    it('names the phase and the share done', () => {
        expect(evaluationProgress({ phase: 'fetching_images', progress: { done: 35, total: 140, label: 'fetching images' } }))
            .toEqual({ phase: 'fetching_images', done: 35, total: 140, percent: 25 });
    });

    it('has no share while the total is not known yet', () => {
        expect(evaluationProgress({ phase: 'building_panel', progress: { done: 0, total: 0, label: '' } }).percent).toBeNull();
    });

    it('never passes 100 and treats an unknown phase as plain work', () => {
        expect(evaluationProgress({ phase: 'something_new', progress: { done: 9, total: 4, label: '' } }))
            .toEqual({ phase: 'working', done: 9, total: 4, percent: 100 });
    });
});

describe('a problem states what failed and why', () => {
    it('tells a second start that an evaluation is already running', () => {
        expect(evaluationProblem('start', new ApiRequestError('A run is already in progress', 409)))
            .toEqual({ what: 'start', cause: 'already_running' });
    });

    it('sends an expired or non-owner session to sign in again', () => {
        expect(evaluationProblem('download', new ApiRequestError('Owner privileges required for this operation', 403)).cause).toBe('signed_out');
        expect(evaluationProblem('history', new ApiRequestError('Not authenticated', 401)).cause).toBe('signed_out');
    });

    it('says a deleted evaluation is gone', () => {
        expect(evaluationProblem('results', new ApiRequestError('run not found', 404))).toEqual({ what: 'results', cause: 'gone' });
    });

    it('maps a server fault to its plain cause', () => {
        expect(evaluationProblem('start', new ApiRequestError('Internal Server Error', 500))).toEqual({ what: 'start', cause: 'server_fault' });
        expect(evaluationProblem('history', new ApiRequestError('HTTP 502', 502)).cause).toBe('server_fault');
    });

    it('carries none of what the server or the browser said, whatever it was', () => {
        const leaks = [
            new ApiRequestError('Traceback (most recent call last): File "/app/x.py", line 3', 500),
            new ApiRequestError('unknown artifact', 400),
            new Error('ECONNRESET 10.0.0.4:8000'),
            'a bare string'
        ];
        for (const error of leaks) {
            expect(Object.keys(evaluationProblem('delete', error)).sort()).toEqual(['cause', 'what']);
        }
        expect(evaluationProblem('delete', leaks[1]).cause).toBe('refused');
        expect(evaluationProblem('delete', leaks[2]).cause).toBe('refused');
    });

    it('recognises a request that never reached YA-WAMF', () => {
        expect(evaluationProblem('history', new TypeError('Failed to fetch'))).toEqual({ what: 'history', cause: 'unreachable' });
        expect(evaluationProblem('stop', new DOMException('timed out', 'AbortError')).cause).toBe('unreachable');
    });
});

describe('why an evaluation stopped, by the code the server recorded', () => {
    it('knows every code the server writes', () => {
        for (const code of ['no_models', 'models_not_ready', 'finder_needs_provider_check', 'no_test_birds', 'no_test_photos', 'network']) {
            expect(stopCause(code)).toBe(code);
        }
    });

    it('is the honest unknown for anything else, never the text itself', () => {
        expect(stopCause('unexpected')).toBe('unexpected');
        expect(stopCause('ValueError: tensor at 0x7f3a')).toBe('unexpected');
        expect(stopCause('a_code_from_a_newer_server')).toBe('unexpected');
    });

    it('is nothing for an evaluation that did not stop early', () => {
        expect(stopCause(null)).toBeNull();
        expect(stopCause(undefined)).toBeNull();
        expect(stopCause('')).toBeNull();
    });
});

describe('why a model has no provider checks or was skipped', () => {
    it('reads the code, with or without the text older files put after it', () => {
        expect(checkRowProblem('activation_failed')).toBe('activation_failed');
        expect(checkRowProblem('provider_sweep_failed')).toBe('provider_sweep_failed');
        expect(checkRowProblem('provider_sweep_failed: RuntimeError(0x7f3a)')).toBe('provider_sweep_failed');
    });

    it('is unknown for anything else', () => {
        expect(checkRowProblem('Segmentation fault in libopenvino.so')).toBe('unknown');
    });

    it('names the two reasons a model is skipped and nothing else', () => {
        expect(skipReason('activation_failed')).toBe('activation_failed');
        expect(skipReason('reload_failed')).toBe('reload_failed');
        expect(skipReason('OSError: [Errno 2]')).toBe('other');
    });
});

describe('files offered for download', () => {
    it('offers only files the evaluation wrote, in one order', () => {
        expect(evaluationFiles(['device_matrix.json', 'summary.json', 'results.jsonl']).map((file) => file.name))
            .toEqual(['summary.json', 'results.jsonl', 'device_matrix.json']);
    });

    it('labels each by what it holds and ignores a file it does not know', () => {
        expect(evaluationFiles(['confusions.csv', 'notes.txt'])).toEqual([{ name: 'confusions.csv', label: 'mix_ups' }]);
    });

    it('offers nothing while the evaluation has written no file', () => {
        expect(evaluationFiles(undefined)).toEqual([]);
        expect(evaluationFiles([])).toEqual([]);
    });
});

function model(overrides: Partial<ModelEvalModelSummary>): ModelEvalModelSummary {
    return {
        model_id: 'small_birds', ready: true, images_evaluated: 120, top1_accuracy: 0.8, top3_accuracy: 0.9,
        top5_accuracy: 0.95, abstention_rate: 0, high_confidence_unknown_rate: 0, shared_core_top1: 0.8,
        regional_top1: 0.7, warnings: [], ...overrides
    };
}

describe('a warning in owner language', () => {
    it('carries the measured figures for a slow run', () => {
        const slow = model({ mean_latency_ms: 2400.4, startup_benchmark_ms: 310.2 });
        expect(warningCopy(slow, { code: 'latency_drift_high', message: 'x', severity: 'critical' }))
            .toEqual({ key: 'latency_drift_high', values: { measured: 2400, loaded: 310 } });
    });

    it('carries how many species a regional model cannot name', () => {
        const regional = model({ vocabulary_known: true, panel_species: 141, species_outside_vocabulary: 25 });
        expect(warningCopy(regional, { code: 'partial_vocabulary', message: 'x', severity: 'info' }))
            .toEqual({ key: 'partial_vocabulary', values: { outside: 25, total: 141 } });
    });

    it('carries the share of photos a model gave no species for', () => {
        expect(warningCopy(model({ abstention_rate: 0.234 }), { code: 'high_abstention', message: 'x', severity: 'warning' }))
            .toEqual({ key: 'high_abstention', values: { share: 23 } });
    });

    it('falls back to the plain form when the figures are missing', () => {
        expect(warningCopy(model({}), { code: 'latency_drift_high', message: 'x', severity: 'critical' }))
            .toEqual({ key: 'latency_drift_high_plain', values: {} });
    });

    it('knows the codes without figures and gives an unknown code its own sentence', () => {
        for (const code of ['low_shared_core', 'provider_fallback_active', 'incomplete_install', 'inference_health_unhealthy', 'region_mismatch']) {
            expect(warningCopy(model({}), { code, message: 'x', severity: 'warning' })).toEqual({ key: code, values: {} });
        }
        for (const code of ['provider_validation_failed', 'provider_validation_partial']) {
            expect(warningCopy(model({}), { code, message: 'x', severity: 'critical' })).toEqual({ key: code, values: {} });
        }
        // The server's words are never the copy: an unknown code has its own honest sentence.
        expect(warningCopy(model({}), { code: 'brand_new', message: 'server words', severity: 'info' })).toEqual({ key: 'unknown', values: {} });
    });
});

const matrix: DeviceMatrix = {
    run_id: 'r', generated_at: 'now', devices: ['cpu', 'intel_gpu', 'intel_npu'],
    models: {
        small_birds: {
            baseline_provider: 'cpu',
            providers: {
                cpu: { compiles: true, baseline: true, images_evaluated: 24 },
                intel_gpu: { compiles: true, finite: true, matches_cpu: true, images_compared: 24 },
                intel_npu: { compiles: true, finite: true, matches_cpu: false, images_compared: 24, top1_match_rate: 0.75 }
            }
        },
        broken: { error: 'activation failed' },
        strange: {
            providers: {
                cpu: { compiles: false },
                intel_gpu: { compiles: true, finite: false },
                intel_npu: { compiles: true }
            }
        }
    },
    crop_detectors: {
        finder: {
            comparison_kind: 'crop_box',
            providers: {
                intel_gpu: { compiles: true, matches_cpu: true, images_compared: 27, mean_box_iou: 0.97 },
                intel_npu: { compiles: true, images_compared: 20, detection_match_rate: 0.9 }
            }
        }
    }
};

describe('one provider check in a model row', () => {
    it('marks the reference provider with the photos it was measured on', () => {
        expect(providerCheck(matrix.models.small_birds, 'cpu')).toEqual({ kind: 'reference', photos: 24 });
    });

    it('passes a provider that agreed on every photo', () => {
        expect(providerCheck(matrix.models.small_birds, 'intel_gpu')).toEqual({ kind: 'same', photos: 24, boxes: false });
    });

    it('counts the photos a differing provider still agreed on', () => {
        expect(providerCheck(matrix.models.small_birds, 'intel_npu')).toEqual({ kind: 'differs', same: 18, photos: 24, boxes: false });
    });

    it('says a bird finder was compared on its boxes', () => {
        expect(providerCheck(matrix.crop_detectors?.finder, 'intel_gpu')).toEqual({ kind: 'same', photos: 27, boxes: true });
        expect(providerCheck(matrix.crop_detectors?.finder, 'intel_npu')).toEqual({ kind: 'differs', same: 18, photos: 20, boxes: true });
    });

    it('separates a provider that would not load from one that gave unusable numbers', () => {
        expect(providerCheck(matrix.models.strange, 'cpu')).toEqual({ kind: 'did_not_load' });
        expect(providerCheck(matrix.models.strange, 'intel_gpu')).toEqual({ kind: 'unusable_output' });
    });

    it('says only that a provider ran when nothing was compared', () => {
        expect(providerCheck(matrix.models.strange, 'intel_npu')).toEqual({ kind: 'ran' });
    });

    it('never claims a result for a provider or a model that was not tested', () => {
        expect(providerCheck(matrix.models.small_birds, 'cuda')).toEqual({ kind: 'not_tested' });
        expect(providerCheck(matrix.models.broken, 'cpu')).toEqual({ kind: 'not_tested' });
        expect(providerCheck(undefined, 'cpu')).toEqual({ kind: 'not_tested' });
    });
});

describe('what checking every model would download', () => {
    const registry = [
        { id: 'small', file_size_mb: 12.4 },
        { id: 'large', file_size_mb: 760 },
        { id: 'finder', file_size_mb: 19.3, artifact_kind: 'crop_detector' },
        { id: 'garden', file_size_mb: 300, artifact_kind: 'garden_animals' }
    ];

    it('counts the bird models and bird finders that are not installed and ready', () => {
        const estimate = missingModelDownload(registry, [{ id: 'small', ready: true }, { id: 'large', ready: false }]);
        expect(estimate).toEqual({ count: 2, megabytes: 779.3, unknownSizes: 0 });
        expect(downloadStatement(estimate)).toBe('sized');
    });

    it('is nothing when every model is installed', () => {
        const estimate = missingModelDownload(registry, [{ id: 'small', ready: true }, { id: 'large', ready: true }, { id: 'finder', ready: true }]);
        expect(estimate).toEqual({ count: 0, megabytes: 0, unknownSizes: 0 });
        expect(downloadStatement(estimate)).toBe('nothing');
    });

    it('keeps a model whose size the registry does not know apart from the measured total', () => {
        const withUnknown = [...registry, { id: 'bundled', file_size_mb: 0 }, { id: 'broken', file_size_mb: Number.NaN }];
        const estimate = missingModelDownload(withUnknown, [{ id: 'large', ready: true }, { id: 'finder', ready: true }]);
        expect(estimate).toEqual({ count: 3, megabytes: 12.4, unknownSizes: 2 });
        expect(downloadStatement(estimate)).toBe('partly_sized');
    });

    it('never states a size when none of the missing models has one', () => {
        const estimate = missingModelDownload([{ id: 'a', file_size_mb: 0 }, { id: 'b', file_size_mb: 0 }], []);
        expect(estimate).toEqual({ count: 2, megabytes: 0, unknownSizes: 2 });
        expect(downloadStatement(estimate)).toBe('unsized');
    });
});
