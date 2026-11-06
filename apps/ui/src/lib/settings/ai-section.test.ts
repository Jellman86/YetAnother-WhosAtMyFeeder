import { describe, expect, it } from 'vitest';
import type { Settings } from '../api/settings';
import { aiSection, editAiDraft } from './ai-section';
import { getRecommendedLlmModel } from './llm-models';
import { sectionIsDirty } from './section-adapter';

function saved(fields: Partial<Settings>): Settings {
    return fields as Settings;
}

describe('AI section draft', () => {
    it('loads Gemini with its recommended model when nothing is saved', () => {
        expect(aiSection.decode(saved({}))).toEqual({
            llmEnabled: false,
            llmProvider: 'gemini',
            llmApiKey: '',
            llmApiKeySaved: false,
            llmModel: getRecommendedLlmModel('gemini'),
            llmAnalysisPromptTemplate: '',
            llmConversationPromptTemplate: '',
            llmChartPromptTemplate: '',
            aiPricingJson: '[]'
        });
    });

    it('never shows a stored key and sends an empty key so the stored one is kept', () => {
        const stored = saved({ llm_enabled: true, llm_provider: 'claude', llm_api_key: '***REDACTED***' });
        const draft = aiSection.decode(stored);
        expect(draft.llmApiKey).toBe('');
        expect(draft.llmApiKeySaved).toBe(true);
        expect(aiSection.encodePatch(draft).llm_api_key).toBe('');
        expect(sectionIsDirty(aiSection, draft, stored)).toBe(false);
    });

    it('moves a retired saved model to its current name without counting that as an edit', () => {
        const stored = saved({ llm_provider: 'openai', llm_model: 'gpt-5.2' });
        const draft = aiSection.decode(stored);
        expect(draft.llmModel).toBe('gpt-5.6');
        expect(sectionIsDirty(aiSection, draft, stored)).toBe(false);
    });

    it('switching provider moves the model to one that provider offers', () => {
        const draft = aiSection.decode(saved({ llm_provider: 'gemini', llm_model: 'gemini-3.1-pro-preview' }));
        const switched = editAiDraft(draft, { llmProvider: 'claude' });
        expect(switched.llmProvider).toBe('claude');
        expect(switched.llmModel).toBe(getRecommendedLlmModel('claude'));
        expect(editAiDraft(draft, { llmModel: 'gemini-3.1-flash-lite' }).llmModel).toBe('gemini-3.1-flash-lite');
    });

    it('typing a key replaces the stored one in what Apply will send', () => {
        const draft = aiSection.decode(saved({ llm_api_key: '***REDACTED***' }));
        const typed = editAiDraft(draft, { llmApiKey: 'sk-new' });
        expect(typed.llmApiKeySaved).toBe(false);
        expect(aiSection.encodePatch(typed).llm_api_key).toBe('sk-new');
        expect(sectionIsDirty(aiSection, typed, saved({ llm_api_key: '***REDACTED***' }))).toBe(true);
    });
});
