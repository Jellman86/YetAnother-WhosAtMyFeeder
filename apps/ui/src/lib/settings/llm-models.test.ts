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
            'gemini-3.1-flash-lite',
            'gemini-3.1-pro-preview'
        ]);

        expect(getLlmModelOptions('openai').map((model) => model.value)).toEqual([
            'gpt-5.6',
            'gpt-5.6-terra',
            'gpt-5.6-luna'
        ]);

        expect(getLlmModelOptions('claude').map((model) => model.value)).toEqual([
            'claude-opus-4-8',
            'claude-haiku-4-5',
            'claude-sonnet-4-6'
        ]);

        expect(getLlmModelOptions('openrouter').map((model) => model.value)).toEqual([
            'google/gemini-3.1-flash-lite',
            'google/gemini-3.1-pro-preview',
            'openai/gpt-5.6-sol',
            'anthropic/claude-opus-4.8'
        ]);
    });

    it('returns the current recommended model per provider', () => {
        expect(getRecommendedLlmModel('gemini')).toBe('gemini-3.1-flash-lite');
        expect(getRecommendedLlmModel('openai')).toBe('gpt-5.6');
        expect(getRecommendedLlmModel('claude')).toBe('claude-opus-4-8');
        expect(getRecommendedLlmModel('openrouter')).toBe('google/gemini-3.1-flash-lite');
    });

    it('maps deprecated saved preset ids to the current equivalents', () => {
        expect(resolveStoredLlmModel('gemini', 'gemini-2.5-flash')).toBe('gemini-3.1-flash-lite');
        expect(resolveStoredLlmModel('openai', 'gpt-5.4')).toBe('gpt-5.6');
        expect(resolveStoredLlmModel('claude', 'claude-opus-4-6')).toBe('claude-opus-4-8');
        expect(resolveStoredLlmModel('openrouter', 'google/gemini-2.5-flash')).toBe('google/gemini-3.1-flash-lite');
    });

    it('preserves custom saved model ids for the same provider', () => {
        expect(resolveStoredLlmModel('openai', 'gpt-5.4-2026-03-01')).toBe('gpt-5.4-2026-03-01');
        expect(resolveStoredLlmModel('claude', 'claude-sonnet-4-5-20250929')).toBe('claude-sonnet-4-5-20250929');
    });

    it('falls back to the provider default when switching to an incompatible provider', () => {
        expect(coerceLlmModelForProvider('openai', 'not-a-real-model')).toBe('gpt-5.6');
        expect(coerceLlmModelForProvider('claude', '')).toBe('claude-opus-4-8');
        expect(coerceLlmModelForProvider('claude', 'gpt-5.4-2026-03-01')).toBe('claude-opus-4-8');
    });

    it('accepts any non-empty model id for openrouter', () => {
        expect(coerceLlmModelForProvider('openrouter', 'google/gemini-3.1-pro-preview')).toBe('google/gemini-3.1-pro-preview');
        expect(coerceLlmModelForProvider('openrouter', 'mistralai/mistral-large')).toBe('mistralai/mistral-large');
        expect(coerceLlmModelForProvider('openrouter', '')).toBe('google/gemini-3.1-flash-lite');
    });
});
