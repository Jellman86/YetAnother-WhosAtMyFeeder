export type LlmProvider = 'gemini' | 'openai' | 'claude' | 'openrouter';

export type LlmModelOption = {
    value: string;
    label: string;
};

const LLM_MODEL_OPTIONS: Record<LlmProvider, LlmModelOption[]> = {
    gemini: [
        { value: 'gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite' },
        { value: 'gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro (Preview)' }
    ],
    openai: [
        { value: 'gpt-5.6', label: 'GPT-5.6' },
        { value: 'gpt-5.6-terra', label: 'GPT-5.6 Terra' },
        { value: 'gpt-5.6-luna', label: 'GPT-5.6 Luna' }
    ],
    claude: [
        { value: 'claude-opus-4-8', label: 'Claude Opus 4.8' },
        { value: 'claude-haiku-4-5', label: 'Claude Haiku 4.5' },
        { value: 'claude-sonnet-4-6', label: 'Claude Sonnet 4.6' }
    ],
    openrouter: [
        { value: 'google/gemini-3.1-flash-lite', label: 'Gemini 3.1 Flash-Lite' },
        { value: 'google/gemini-3.1-pro-preview', label: 'Gemini 3.1 Pro (Preview)' },
        { value: 'openai/gpt-5.6-sol', label: 'GPT-5.6 Sol' },
        { value: 'anthropic/claude-opus-4.8', label: 'Claude Opus 4.8' }
    ]
};

const RECOMMENDED_LLM_MODEL: Record<LlmProvider, string> = {
    gemini: 'gemini-3.1-flash-lite',
    openai: 'gpt-5.6',
    claude: 'claude-opus-4-8',
    openrouter: 'google/gemini-3.1-flash-lite'
};

const LLM_MODEL_ALIASES: Record<LlmProvider, Record<string, string>> = {
    gemini: {
        'gemini-2.5-flash': 'gemini-3.1-flash-lite',
        'gemini-2.5-flash-lite': 'gemini-3.1-flash-lite',
        'gemini-2.5-pro': 'gemini-3.1-pro-preview'
    },
    openai: {
        'gpt-5.2': 'gpt-5.6',
        'gpt-5.2-pro': 'gpt-5.6',
        'gpt-5.4': 'gpt-5.6',
        'gpt-5.4-pro': 'gpt-5.6'
    },
    claude: {
        'claude-sonnet-4-5': 'claude-sonnet-4-6',
        'claude-opus-4-6': 'claude-opus-4-8',
        'claude-opus-4-7': 'claude-opus-4-8'
    },
    openrouter: {
        'google/gemini-2.5-flash-preview': 'google/gemini-3.1-flash-lite',
        'google/gemini-2.5-flash': 'google/gemini-3.1-flash-lite',
        'openai/gpt-4o-mini': 'openai/gpt-5.6-sol',
        'anthropic/claude-3.5-haiku': 'anthropic/claude-opus-4.8'
    }
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

    // OpenRouter exposes thousands of models — accept any non-empty ID, not just presets.
    if (normalizedProvider === 'openrouter' && resolved) {
        return resolved;
    }

    const options = LLM_MODEL_OPTIONS[normalizedProvider];

    if (options.some((option) => option.value === resolved)) {
        return resolved;
    }

    return RECOMMENDED_LLM_MODEL[normalizedProvider];
}
