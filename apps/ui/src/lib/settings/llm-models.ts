export type LlmProvider = 'gemini' | 'openai' | 'claude' | 'openrouter';

export type LlmModelOption = {
    value: string;
    label: string;
};

const LLM_MODEL_OPTIONS: Record<LlmProvider, LlmModelOption[]> = {
    gemini: [
        { value: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
        { value: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash Lite' },
        { value: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' }
    ],
    openai: [
        { value: 'gpt-5.4', label: 'GPT-5.4' },
        { value: 'gpt-5-mini', label: 'GPT-5 mini' },
        { value: 'gpt-5.4-pro', label: 'GPT-5.4 Pro' }
    ],
    claude: [
        { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
        { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
        { value: 'claude-opus-4-6', label: 'Claude Opus 4.6' }
    ],
    openrouter: [
        { value: 'google/gemini-2.5-flash-preview', label: 'Gemini 2.5 Flash' },
        { value: 'openai/gpt-4o-mini', label: 'GPT-4o Mini' },
        { value: 'anthropic/claude-3.5-haiku', label: 'Claude 3.5 Haiku' },
        { value: 'meta-llama/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' }
    ]
};

const RECOMMENDED_LLM_MODEL: Record<LlmProvider, string> = {
    gemini: 'gemini-2.5-flash',
    openai: 'gpt-5.4',
    claude: 'claude-sonnet-4-6',
    openrouter: 'google/gemini-2.5-flash-preview'
};

const LLM_MODEL_ALIASES: Record<LlmProvider, Record<string, string>> = {
    gemini: {},
    openai: {
        'gpt-5.2': 'gpt-5.4',
        'gpt-5.2-pro': 'gpt-5.4-pro'
    },
    claude: {
        'claude-sonnet-4-5': 'claude-sonnet-4-6'
    },
    openrouter: {}
};

function normalizeProvider(provider: string): LlmProvider {
    if (provider === 'openai' || provider === 'claude' || provider === 'openrouter') return provider;
    return 'gemini';
}

export function getLlmModelOptions(provider: string): LlmModelOption[] {
    return LLM_MODEL_OPTIONS[normalizeProvider(provider)];
}

export function getRecommendedLlmModel(provider: string): string {
    return RECOMMENDED_LLM_MODEL[normalizeProvider(provider)];
}

function resolveAliasedLlmModel(provider: LlmProvider, model: string | null | undefined): string {
    const candidate = String(model || '').trim();
    return LLM_MODEL_ALIASES[provider][candidate] ?? candidate;
}

export function resolveStoredLlmModel(provider: string, model: string | null | undefined): string {
    const normalizedProvider = normalizeProvider(provider);
    const aliased = resolveAliasedLlmModel(normalizedProvider, model);

    if (aliased) {
        return aliased;
    }

    return RECOMMENDED_LLM_MODEL[normalizedProvider];
}

export function coerceLlmModelForProvider(provider: string, model: string | null | undefined): string {
    const normalizedProvider = normalizeProvider(provider);
    const resolved = resolveStoredLlmModel(normalizedProvider, model);
    const options = LLM_MODEL_OPTIONS[normalizedProvider];

    if (options.some((option) => option.value === resolved)) {
        return resolved;
    }

    return RECOMMENDED_LLM_MODEL[normalizedProvider];
}
