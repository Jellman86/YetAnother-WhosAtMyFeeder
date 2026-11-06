import type { Settings } from '../api/settings';
import { coerceLlmModelForProvider, getRecommendedLlmModel, resolveStoredLlmModel } from './llm-models';
import type { SettingsSectionAdapter } from './section-adapter';

const REDACTED = '***REDACTED***';

/** The AI tab's part of the Settings draft. `llmApiKeySaved` says a key is stored but not shown. */
export interface AiDraft {
    llmEnabled: boolean;
    llmProvider: string;
    llmApiKey: string;
    llmApiKeySaved: boolean;
    llmModel: string;
    llmAnalysisPromptTemplate: string;
    llmConversationPromptTemplate: string;
    llmChartPromptTemplate: string;
    aiPricingJson: string;
}

interface AiPatch {
    llm_enabled: boolean;
    llm_provider: string;
    llm_api_key: string;
    llm_model: string;
    llm_analysis_prompt_template: string;
    llm_conversation_prompt_template: string;
    llm_chart_prompt_template: string;
    ai_pricing_json: string;
}

export const aiSection: SettingsSectionAdapter<AiDraft, AiPatch> = {
    decode(saved: Settings): AiDraft {
        const llmProvider = saved.llm_provider ?? 'gemini';
        const llmApiKeySaved = saved.llm_api_key === REDACTED;
        return {
            llmEnabled: saved.llm_enabled ?? false,
            llmProvider,
            // A stored key is never shown; the field stays empty and an empty key keeps it.
            llmApiKey: llmApiKeySaved ? '' : saved.llm_api_key ?? '',
            llmApiKeySaved,
            llmModel: resolveStoredLlmModel(llmProvider, saved.llm_model ?? getRecommendedLlmModel(llmProvider)),
            llmAnalysisPromptTemplate: saved.llm_analysis_prompt_template ?? '',
            llmConversationPromptTemplate: saved.llm_conversation_prompt_template ?? '',
            llmChartPromptTemplate: saved.llm_chart_prompt_template ?? '',
            aiPricingJson: saved.ai_pricing_json ?? '[]'
        };
    },
    encodePatch(draft: AiDraft): AiPatch {
        return {
            llm_enabled: draft.llmEnabled,
            llm_provider: draft.llmProvider,
            llm_api_key: draft.llmApiKey,
            llm_model: draft.llmModel,
            llm_analysis_prompt_template: draft.llmAnalysisPromptTemplate,
            llm_conversation_prompt_template: draft.llmConversationPromptTemplate,
            llm_chart_prompt_template: draft.llmChartPromptTemplate,
            ai_pricing_json: draft.aiPricingJson
        };
    }
};

/**
 * Apply an edit from the AI tab. Switching provider moves the model to one that provider offers,
 * and typing a new key means the stored one is no longer what will be saved.
 */
export function editAiDraft(draft: AiDraft, edit: Partial<AiDraft>): AiDraft {
    const next = { ...draft, ...edit };
    if (edit.llmProvider !== undefined && edit.llmProvider !== draft.llmProvider) {
        next.llmModel = coerceLlmModelForProvider(next.llmProvider, next.llmModel);
    }
    if (next.llmApiKeySaved && next.llmApiKey) next.llmApiKeySaved = false;
    return next;
}
