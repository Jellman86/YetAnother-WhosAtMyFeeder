<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { onMount } from 'svelte';
    import SecretSavedBadge from './SecretSavedBadge.svelte';
    import { fetchAiUsage, clearAiUsage, type AIUsageResponse } from '../../api';
    import { toastStore } from '../../stores/toast.svelte';
    import { getRecommendedLlmModel } from '../../settings/llm-models';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import SettingsInput from './_primitives/SettingsInput.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import SettingsTextarea from './_primitives/SettingsTextarea.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    let {
        llmEnabled = $bindable(false),
        llmProvider = $bindable('gemini'),
        llmApiKey = $bindable(''),
        llmApiKeySaved = $bindable(false),
        llmModel = $bindable(getRecommendedLlmModel('gemini')),
        llmAnalysisPromptTemplate = $bindable(''),
        llmConversationPromptTemplate = $bindable(''),
        llmChartPromptTemplate = $bindable(''),
        llmPromptStyle = $bindable('classic'),
        aiPricingJson = $bindable('[]'),
        availableModels = [],
        onTestConnection,
        onApplyStyle,
        onResetDefaults
    }: {
        llmEnabled: boolean;
        llmProvider: string;
        llmApiKey: string;
        llmApiKeySaved: boolean;
        llmModel: string;
        llmAnalysisPromptTemplate: string;
        llmConversationPromptTemplate: string;
        llmChartPromptTemplate: string;
        llmPromptStyle: string;
        aiPricingJson: string;
        availableModels: { value: string; label: string }[];
        onTestConnection: () => Promise<void>;
        onApplyStyle: () => void;
        onResetDefaults: () => void;
    } = $props();

    let usage = $state<AIUsageResponse | null>(null);
    let loadingUsage = $state(true);
    let clearingUsage = $state(false);
    let usageLoadError = $state<string | null>(null);

    async function loadUsage() {
        loadingUsage = true;
        usageLoadError = null;
        try {
            usage = await fetchAiUsage('30d');
        } catch (e) {
            usage = null;
            usageLoadError = $_('settings.ai.usage_load_error', { default: 'Failed to load AI usage.' });
            console.error('Failed to fetch AI usage', e);
        } finally {
            loadingUsage = false;
        }
    }

    async function handleClearUsage() {
        if (!confirm($_('settings.ai.clear_usage_confirm', { default: 'Are you sure you want to clear AI usage history? This cannot be undone.' }))) {
            return;
        }
        clearingUsage = true;
        try {
            await clearAiUsage();
            toastStore.success($_('settings.ai.clear_usage_success', { default: 'AI usage history cleared.' }));
            await loadUsage();
        } catch (e) {
            toastStore.error($_('settings.ai.clear_usage_error', { default: 'Failed to clear usage history.' }));
        } finally {
            clearingUsage = false;
        }
    }

    onMount(() => {
        loadUsage();
    });

    const formatTokens = (n: number) => {
        if (n >= 1000000) return `${(n / 1000000).toFixed(2)}M`;
        if (n >= 1000) return `${(n / 1000).toFixed(1)}k`;
        return n.toString();
    };

    const metricCardClass = 'p-6 rounded-2xl border transition-all duration-200 hover:-translate-y-0.5';
    const buttonPrimaryClass = 'px-6 py-3 bg-teal-500 hover:bg-teal-600 text-white text-xs font-black uppercase tracking-widest rounded-2xl active:scale-[0.99] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-teal-400 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed';
    const buttonSecondaryClass = 'px-6 py-3 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-200 text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 active:scale-[0.99] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-slate-300 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed';
</script>

<div class="space-y-6">
    {#snippet usageActions()}
        <button
            type="button"
            onclick={handleClearUsage}
            disabled={clearingUsage || !usage?.calls}
            class="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[10px] font-black uppercase tracking-widest hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 active:scale-[0.99] transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-300 dark:focus:ring-offset-slate-900 disabled:opacity-50 disabled:cursor-not-allowed"
        >
            {clearingUsage ? $_('common.clearing', { default: 'Clearing...' }) : $_('settings.ai.clear_usage', { default: 'Clear History' })}
        </button>
    {/snippet}

    <SettingsCard
        icon="📊"
        title={$_('settings.ai.usage_title', { default: 'AI Usage' })}
        description={$_('settings.ai.usage_subtitle', { default: 'Last 30 days consumption' })}
        actions={usageActions}
    >
        {#if loadingUsage}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 animate-pulse">
                <div class="h-24 rounded-2xl bg-slate-100 dark:bg-slate-800/50"></div>
                <div class="h-24 rounded-2xl bg-slate-100 dark:bg-slate-800/50"></div>
                <div class="h-24 rounded-2xl bg-slate-100 dark:bg-slate-800/50"></div>
            </div>
        {:else if usage}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div class="{metricCardClass} bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">{$_('settings.ai.total_calls', { default: 'API Requests' })}</p>
                    <p class="text-2xl font-black text-slate-900 dark:text-white">{usage.calls.toLocaleString()}</p>
                </div>
                <div class="{metricCardClass} bg-slate-50 dark:bg-slate-900/50 border-slate-100 dark:border-slate-700/50">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">{$_('settings.ai.total_tokens', { default: 'Tokens Consumed' })}</p>
                    <p class="text-2xl font-black text-slate-900 dark:text-white">{formatTokens(usage.total_tokens)}</p>
                    <p class="text-[9px] font-bold text-slate-400 mt-1">{formatTokens(usage.input_tokens)} in / {formatTokens(usage.output_tokens)} out</p>
                </div>
                <div class="{metricCardClass} bg-emerald-500/5 dark:bg-emerald-500/10 border-emerald-500/10 dark:border-emerald-500/20">
                    <p class="text-[10px] font-black uppercase tracking-widest text-emerald-600 dark:text-emerald-400 mb-1">{$_('settings.ai.estimated_cost', { default: 'Estimated Cost' })}</p>
                    <p class="text-2xl font-black text-emerald-700 dark:text-emerald-300">
                        ${usage.estimated_cost_usd.toFixed(4)}
                        <span class="text-xs ml-1 font-bold text-emerald-600/60 dark:text-emerald-400/40">USD</span>
                    </p>
                    {#if !usage.pricing_configured}
                        <p class="text-[9px] font-bold text-amber-600 dark:text-amber-400 mt-1">{$_('settings.ai.pricing_not_configured', { default: 'Configure pricing below for accuracy' })}</p>
                    {/if}
                </div>
            </div>

            {#if usage.breakdown.length > 0}
                <div class="overflow-hidden rounded-2xl border border-slate-100 dark:border-slate-700/50">
                    <table class="w-full text-left text-xs">
                        <thead class="bg-slate-50 dark:bg-slate-900/60 text-[10px] font-black uppercase tracking-widest text-slate-400">
                            <tr>
                                <th class="px-4 py-3">{$_('settings.ai.table_model', { default: 'Model' })}</th>
                                <th class="px-4 py-3">{$_('settings.ai.table_feature', { default: 'Feature' })}</th>
                                <th class="px-4 py-3 text-right">{$_('settings.ai.table_calls', { default: 'Calls' })}</th>
                                <th class="px-4 py-3 text-right">{$_('settings.ai.table_tokens', { default: 'Tokens' })}</th>
                                <th class="px-4 py-3 text-right">{$_('settings.ai.table_cost', { default: 'Cost' })}</th>
                            </tr>
                        </thead>
                        <tbody class="divide-y divide-slate-100 dark:divide-slate-700/50">
                            {#each usage.breakdown as item}
                                <tr class="text-slate-700 dark:text-slate-300 transition-colors hover:bg-slate-50/70 dark:hover:bg-slate-900/40">
                                    <td class="px-4 py-3 font-bold">
                                        <span class="opacity-50 font-black uppercase text-[9px] mr-1">{item.provider}</span>
                                        {item.model}
                                    </td>
                                    <td class="px-4 py-3 capitalize">{item.feature}</td>
                                    <td class="px-4 py-3 text-right">{item.calls}</td>
                                    <td class="px-4 py-3 text-right font-mono">{formatTokens(item.total_tokens)}</td>
                                    <td class="px-4 py-3 text-right font-bold text-emerald-600 dark:text-emerald-400">${item.estimated_cost_usd.toFixed(4)}</td>
                                </tr>
                            {/each}
                        </tbody>
                    </table>
                </div>
            {/if}
        {:else}
            <div class="p-12 text-center rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-700/50">
                <p class="text-sm font-bold text-slate-400">
                    {usageLoadError ?? $_('settings.ai.no_usage_data', { default: 'No AI usage recorded yet.' })}
                </p>
            </div>
        {/if}
    </SettingsCard>

    <SettingsCard
        icon="🤖"
        title={$_('settings.ai.connection_title', { default: 'Model Configuration' })}
    >
        <SettingsRow
            labelId="setting-llm-enabled"
            label={$_('settings.llm.enabled')}
        >
            <SettingsToggle
                checked={llmEnabled}
                labelledBy="setting-llm-enabled"
                srLabel={$_('settings.llm.enabled')}
                onchange={(v) => (llmEnabled = v)}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-llm-provider"
            label={$_('settings.llm.provider')}
            layout="stacked"
        >
            <SettingsSegmented
                value={llmProvider}
                ariaLabelTemplate={(label) => label}
                onchange={(v) => (llmProvider = v)}
                options={[
                    { value: 'gemini', label: 'Gemini' },
                    { value: 'openai', label: 'OpenAI' },
                    { value: 'claude', label: 'Claude' },
                    { value: 'openrouter', label: 'OpenRouter' }
                ]}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-llm-api-key"
            label={$_('settings.llm.api_key')}
            layout="stacked"
        >
            <div class="space-y-2">
                {#if llmApiKeySaved}
                    <div class="flex justify-end"><SecretSavedBadge /></div>
                {/if}
                <SettingsInput
                    id="llm-api-key"
                    type="password"
                    autocomplete="off"
                    value={llmApiKey}
                    placeholder={llmApiKeySaved ? '***REDACTED***' : 'sk-...'}
                    ariaLabel={$_('settings.llm.api_key')}
                    oninput={(v) => (llmApiKey = v)}
                />
            </div>
        </SettingsRow>

        <SettingsRow
            labelId="setting-llm-model"
            label={$_('settings.llm.model')}
            description={llmProvider === 'openrouter'
                ? $_('settings.llm.openrouter_model_hint', { default: 'Enter any OpenRouter model ID (e.g. google/gemini-2.5-flash). Browse models at openrouter.ai/models.' })
                : $_('settings.llm.recommended_model', { values: { model: getRecommendedLlmModel(llmProvider) }, default: `Recommended: ${getRecommendedLlmModel(llmProvider)}` })}
            layout="stacked"
        >
            {#if llmProvider === 'openrouter'}
                <datalist id="llm-model-suggestions">
                    {#each availableModels as model}
                        <option value={model.value}>{model.label}</option>
                    {/each}
                </datalist>
                <input
                    id="llm-model"
                    type="text"
                    list="llm-model-suggestions"
                    bind:value={llmModel}
                    placeholder={getRecommendedLlmModel(llmProvider)}
                    aria-label={$_('settings.llm.model')}
                    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all"
                />
            {:else}
                <SettingsSelect
                    id="llm-model"
                    value={llmModel}
                    ariaLabel={$_('settings.llm.model')}
                    options={availableModels}
                    onchange={(v) => (llmModel = v)}
                />
            {/if}
        </SettingsRow>

        <button
            type="button"
            onclick={onTestConnection}
            disabled={!llmApiKey && !llmApiKeySaved}
            class="w-full {buttonPrimaryClass}"
        >
            {$_('settings.llm.test_connection')}
        </button>

        <div class="rounded-2xl border border-slate-100 dark:border-slate-700/50 bg-slate-50 dark:bg-slate-900/50 p-4 text-xs text-slate-600 dark:text-slate-300">
            <p class="font-bold mb-2 text-slate-700 dark:text-slate-200">{$_('settings.ai.provider_info_title', { default: 'Cloud AI Providers' })}</p>
            <p class="leading-relaxed">{$_('settings.ai.provider_info_desc', { default: 'YA-WAMF uses cloud LLMs for behavioral analysis and natural language interactions. You will need your own API key from the provider.' })}</p>
            <div class="mt-3 grid grid-cols-2 gap-2">
                <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" class="text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline focus:outline-none focus:ring-2 focus:ring-teal-300 rounded uppercase tracking-widest">{$_('settings.llm.get_gemini_key', { default: 'Get Google Gemini Key →' })}</a>
                <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" class="text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline focus:outline-none focus:ring-2 focus:ring-teal-300 rounded uppercase tracking-widest">{$_('settings.llm.get_openai_key', { default: 'Get OpenAI Key →' })}</a>
                <a href="https://console.anthropic.com/" target="_blank" rel="noopener noreferrer" class="text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline focus:outline-none focus:ring-2 focus:ring-teal-300 rounded uppercase tracking-widest">{$_('settings.llm.get_claude_key', { default: 'Get Anthropic Claude Key →' })}</a>
                <a href="https://openrouter.ai/keys" target="_blank" rel="noopener noreferrer" class="text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline focus:outline-none focus:ring-2 focus:ring-teal-300 rounded uppercase tracking-widest">{$_('settings.llm.get_openrouter_key', { default: 'Get OpenRouter Key →' })}</a>
            </div>
        </div>

        <AdvancedSection
            id="ai-pricing-and-prompts"
            title={$_('settings.ai.advanced_title', { default: 'Pricing & prompt templates' })}
        >
            <SettingsRow
                labelId="setting-ai-pricing"
                label={$_('settings.ai.pricing_json', { default: 'Pricing Registry (JSON)' })}
                description={$_('settings.ai.pricing_help', { default: 'Override the default token pricing for cost estimation. Format: an array of objects with provider, model, inputPer1M, and outputPer1M.' })}
                layout="stacked"
            >
                <div class="space-y-2">
                    <div class="flex justify-end">
                        <a href="https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/main/docs/ai-pricing.json" target="_blank" rel="noopener noreferrer" class="text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline uppercase tracking-widest">
                            {$_('settings.ai.view_reference_pricing', { default: 'View Reference Pricing →' })}
                        </a>
                    </div>
                    <SettingsTextarea
                        id="ai-pricing-json"
                        value={aiPricingJson}
                        rows={8}
                        font="mono"
                        ariaLabel={$_('settings.ai.pricing_json', { default: 'Pricing Registry (JSON)' })}
                        placeholder={'[{"provider": "gemini", "model": "*", "inputPer1M": 0.3, "outputPer1M": 2.5}]'}
                        oninput={(v) => (aiPricingJson = v)}
                    />
                </div>
            </SettingsRow>

            <SettingsRow
                labelId="setting-llm-prompt-style"
                label={$_('settings.debug.llm_prompt_style_label')}
                layout="stacked"
            >
                <div class="grid grid-cols-1 sm:grid-cols-2 gap-2">
                    <SettingsSelect
                        id="llm-prompt-style"
                        value={llmPromptStyle}
                        ariaLabel={$_('settings.debug.llm_prompt_style_label')}
                        options={[
                            { value: 'classic', label: $_('settings.debug.llm_prompt_style_classic') },
                            { value: 'field', label: $_('settings.debug.llm_prompt_style_field') }
                        ]}
                        onchange={(v) => (llmPromptStyle = v)}
                    />
                    <div class="flex gap-2">
                        <button type="button" onclick={onApplyStyle} class="flex-1 {buttonPrimaryClass}">
                            {$_('settings.debug.llm_prompt_apply_style')}
                        </button>
                        <button type="button" onclick={onResetDefaults} class="flex-1 {buttonSecondaryClass}">
                            {$_('settings.debug.llm_prompt_reset_defaults')}
                        </button>
                    </div>
                </div>
            </SettingsRow>

            <SettingsRow
                labelId="setting-llm-prompt-analysis"
                label={$_('settings.debug.llm_prompt_analysis')}
                description={$_('settings.debug.llm_prompt_analysis_hint')}
                layout="stacked"
            >
                <SettingsTextarea
                    id="llm-prompt-analysis"
                    value={llmAnalysisPromptTemplate}
                    rows={6}
                    font="mono"
                    ariaLabel={$_('settings.debug.llm_prompt_analysis')}
                    oninput={(v) => (llmAnalysisPromptTemplate = v)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-llm-prompt-conversation"
                label={$_('settings.debug.llm_prompt_conversation')}
                description={$_('settings.debug.llm_prompt_conversation_hint')}
                layout="stacked"
            >
                <SettingsTextarea
                    id="llm-prompt-conversation"
                    value={llmConversationPromptTemplate}
                    rows={6}
                    font="mono"
                    ariaLabel={$_('settings.debug.llm_prompt_conversation')}
                    oninput={(v) => (llmConversationPromptTemplate = v)}
                />
            </SettingsRow>

            <SettingsRow
                labelId="setting-llm-prompt-chart"
                label={$_('settings.debug.llm_prompt_chart')}
                description={$_('settings.debug.llm_prompt_chart_hint')}
                layout="stacked"
            >
                <SettingsTextarea
                    id="llm-prompt-chart"
                    value={llmChartPromptTemplate}
                    rows={6}
                    font="mono"
                    ariaLabel={$_('settings.debug.llm_prompt_chart')}
                    oninput={(v) => (llmChartPromptTemplate = v)}
                />
            </SettingsRow>
        </AdvancedSection>
    </SettingsCard>
</div>
