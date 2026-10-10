import { describe, expect, it } from 'vitest';
import type { ModelEvalModelSummary } from '../api/model_eval';
import { isCompatibilityOnlyRun, modelEvalScores } from './model-eval-scores';

const base: ModelEvalModelSummary = {
    model_id: 'eu_medium_focalnet_b',
    ready: true,
    images_evaluated: 299,
    top1_accuracy: 0.528,
    top3_accuracy: 0.6,
    top5_accuracy: 0.62,
    abstention_rate: 0.04,
    high_confidence_unknown_rate: 0,
    shared_core_top1: 0.386,
    regional_top1: 0.678,
    warnings: [],
};

describe('model evaluation scores', () => {
    it('compares a regional model on the birds it can name', () => {
        const scores = modelEvalScores({
            ...base,
            vocabulary_known: true,
            panel_species: 141,
            species_outside_vocabulary: 26,
            top1_accuracy_in_vocabulary: 0.83,
            top3_accuracy_in_vocabulary: 0.9,
            shared_core_top1_in_vocabulary: 0.86,
            regional_top1_in_vocabulary: 0.81,
        });
        expect(scores).toEqual({ top1: 0.83, top3: 0.9, core: 0.86, region: 0.81, canName: '115 of 141' });
    });

    it('shows no core score when the model can name no core bird, rather than 0%', () => {
        const scores = modelEvalScores({
            ...base,
            vocabulary_known: true,
            panel_species: 3,
            species_outside_vocabulary: 2,
            top1_accuracy_in_vocabulary: 1,
            shared_core_top1_in_vocabulary: null,
            regional_top1_in_vocabulary: 1,
        });
        expect(scores.core).toBeNull();
        expect(scores.canName).toBe('1 of 3');
    });

    it('keeps the figures over every bird for runs that do not know the vocabulary', () => {
        expect(modelEvalScores(base)).toEqual({ top1: 0.528, top3: 0.6, core: 0.386, region: 0.678, canName: null });
        expect(modelEvalScores({ ...base, vocabulary_known: false, top1_accuracy_in_vocabulary: null }).top1).toBe(0.528);
    });

    it('reports no accuracy for a compatibility-only row, whose zeros are placeholders', () => {
        const compatibility: ModelEvalModelSummary = {
            ...base,
            requested_provider: 'validation_sweep',
            active_provider: 'intel_npu',
            top1_accuracy: 0,
            top3_accuracy: 0,
            top5_accuracy: 0,
            shared_core_top1: 0,
            regional_top1: 0,
        };
        expect(modelEvalScores(compatibility)).toEqual({ top1: null, top3: null, core: null, region: null, canName: null });
    });

    it('keeps a genuinely measured zero as zero', () => {
        const measuredZero = modelEvalScores({
            ...base,
            requested_provider: 'intel_npu',
            top1_accuracy: 0,
            top3_accuracy: 0,
            shared_core_top1: 0,
            regional_top1: 0,
        });
        expect(measuredZero).toEqual({ top1: 0, top3: 0, core: 0, region: 0, canName: null });
    });
});

describe('compatibility-only runs', () => {
    it('are recognised from the validation sweep marker, not from zero scores', () => {
        const compatibility = { ...base, requested_provider: 'validation_sweep', top1_accuracy: 0 };
        expect(isCompatibilityOnlyRun([compatibility, { ...compatibility, model_id: 'dino' }])).toBe(true);
        expect(isCompatibilityOnlyRun([{ ...base, top1_accuracy: 0, top3_accuracy: 0 }])).toBe(false);
        expect(isCompatibilityOnlyRun([])).toBe(false);
        expect(isCompatibilityOnlyRun(undefined)).toBe(false);
    });
});
