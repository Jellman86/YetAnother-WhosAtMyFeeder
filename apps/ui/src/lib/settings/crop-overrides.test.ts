import { describe, expect, it } from 'vitest';

import type { ModelMetadata } from '../api/classifier';
import {
    CROP_MODEL_OVERRIDE_VALUES,
    CROP_SOURCE_OVERRIDE_VALUES,
    getCropVariantOverrideEntries,
    normalizeCropModelOverride,
    normalizeCropOverrideMap,
    normalizeCropSourceOverride,
    roundTripCropOverrides,
} from './crop-overrides';

describe('crop override helpers', () => {
    it('normalizes unsupported crop override values to defaults', () => {
        expect(normalizeCropModelOverride(undefined)).toBe('default');
        expect(normalizeCropModelOverride('enabled')).toBe('default');
        expect(normalizeCropSourceOverride(undefined)).toBe('default');
        expect(normalizeCropSourceOverride('hq')).toBe('default');
    });

    it('normalizes override maps and drops default-valued entries from payloads', () => {
        const roundTrip = roundTripCropOverrides(
            {
                small_birds: 'on',
                'small_birds.na': 'nonsense',
                convnext_large_inat21: 'default',
            },
            {
                small_birds: 'high_quality',
                'small_birds.na': 'bad',
                convnext_large_inat21: 'default',
            },
            {
                small_birds: 'off',
                'small_birds.na': 'default',
                convnext_large_inat21: 'default',
            },
            {
                small_birds: 'standard',
                'small_birds.na': 'default',
                convnext_large_inat21: 'default',
            }
        );

        expect(roundTrip.loaded.modelOverrides).toEqual({
            small_birds: 'on',
            'small_birds.na': 'default',
            convnext_large_inat21: 'default',
        });
        expect(roundTrip.loaded.sourceOverrides).toEqual({
            small_birds: 'high_quality',
            'small_birds.na': 'default',
            convnext_large_inat21: 'default',
        });
        expect(roundTrip.payload).toEqual({
            crop_model_overrides: {
                small_birds: 'off',
            },
            crop_source_overrides: {
                small_birds: 'standard',
            },
        });
    });

    it('derives variant override entries from regional family metadata', () => {
        const model: ModelMetadata = {
            id: 'small_birds',
            name: 'Small Birds',
            description: 'Regional birds-only family',
            architecture: 'Regional Birds Family',
            file_size_mb: 18,
            accuracy_tier: 'High',
            inference_speed: 'Medium',
            download_url: 'https://example.invalid/model.onnx',
            labels_url: 'https://example.invalid/labels.txt',
            input_size: 224,
            runtime: 'onnx',
            supported_inference_providers: ['cpu'],
            tier: 'small',
            taxonomy_scope: 'birds_only',
            recommended_for: 'Regional family',
            advanced_only: false,
            sort_order: 10,
            status: 'planned',
            family_id: 'small_birds',
            default_region: 'na',
            region_variants: {
                eu: { name: 'Europe', region_scope: 'eu' },
                na: { name: 'North America', region_scope: 'na' },
            },
            crop_generator: {
                enabled: false,
                source_preference: 'standard',
            },
        };

        expect(getCropVariantOverrideEntries(model)).toEqual([
            {
                id: 'small_birds.eu',
                label: 'Europe',
                region: 'eu',
            },
            {
                id: 'small_birds.na',
                label: 'North America',
                region: 'na',
            },
        ]);
    });

    it('exposes supported override values in UI order', () => {
        expect(CROP_MODEL_OVERRIDE_VALUES).toEqual(['default', 'on', 'off']);
        expect(CROP_SOURCE_OVERRIDE_VALUES).toEqual(['default', 'standard', 'high_quality']);
    });

    it('normalizes arbitrary maps with the provided value normalizer', () => {
        expect(
            normalizeCropOverrideMap(
                { small_birds: 'on', medium_birds: 'bogus' },
                normalizeCropModelOverride
            )
        ).toEqual({
            small_birds: 'on',
            medium_birds: 'default',
        });
    });
});
