import { describe, expect, it } from 'vitest';

import {
    coerceLlmModelForProvider,
    getLlmModelOptions,
    getRecommendedLlmModel,
    resolveStoredLlmModel
} from './llm-models';

describe('llm model presets', () => {
    it('uses the current provider model lineup', () => {
        expect(getLlmModelOptions('gemini').map((model) => model.value)).toEqual([
            'gemini-2.5-flash',
            'gemini-2.5-flash-lite',
            'gemini-2.5-pro'
        ]);

        expect(getLlmModelOptions('openai').map((model) => model.value)).toEqual([
            'gpt-5.4',
            'gpt-5-mini',
            'gpt-5.4-pro'
        ]);

        expect(getLlmModelOptions('claude').map((model) => model.value)).toEqual([
            'claude-sonnet-4-6',
            'claude-haiku-4-5',
            'claude-opus-4-6'
        ]);
    });

    it('returns the current recommended model per provider', () => {
        expect(getRecommendedLlmModel('gemini')).toBe('gemini-2.5-flash');
        expect(getRecommendedLlmModel('openai')).toBe('gpt-5.4');
        expect(getRecommendedLlmModel('claude')).toBe('claude-sonnet-4-6');
    });

    it('maps deprecated saved preset ids to the current equivalents', () => {
        expect(resolveStoredLlmModel('openai', 'gpt-5.2')).toBe('gpt-5.4');
        expect(resolveStoredLlmModel('openai', 'gpt-5.2-pro')).toBe('gpt-5.4-pro');
        expect(resolveStoredLlmModel('claude', 'claude-sonnet-4-5')).toBe('claude-sonnet-4-6');
    });

    it('preserves custom saved model ids for the same provider', () => {
        expect(resolveStoredLlmModel('openai', 'gpt-5.4-2026-03-01')).toBe('gpt-5.4-2026-03-01');
        expect(resolveStoredLlmModel('claude', 'claude-sonnet-4-5-20250929')).toBe('claude-sonnet-4-5-20250929');
    });

    it('falls back to the provider default when switching to an incompatible provider', () => {
        expect(coerceLlmModelForProvider('openai', 'not-a-real-model')).toBe('gpt-5.4');
        expect(coerceLlmModelForProvider('claude', '')).toBe('claude-sonnet-4-6');
        expect(coerceLlmModelForProvider('claude', 'gpt-5.4-2026-03-01')).toBe('claude-sonnet-4-6');
    });
});
