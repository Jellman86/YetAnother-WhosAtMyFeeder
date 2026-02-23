<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { onMount } from 'svelte';
    import { fetchAiUsage, clearAiUsage, type AIUsageResponse, type AIUsageBreakdown } from '../../api';
    import { toastStore } from '../../stores/toast.svelte';

    let {
        llmEnabled = $bindable(false),
        llmProvider = $bindable('gemini'),
        llmApiKey = $bindable(''),
        llmApiKeySaved = $bindable(false),
        llmModel = $bindable('gemini-2.5-flash'),
        llmAnalysisPromptTemplate = $bindable(''),
        llmConversationPromptTemplate = $bindable(''),
        llmChartPromptTemplate = $bindable(''),
        llmPromptStyle = $bindable('classic'),
        aiPricingJson = $bindable('[]'),
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
        onTestConnection: () => Promise<void>;
        onApplyStyle: () => void;
        onResetDefaults: () => void;
    } = $props();

    let usage = $state<AIUsageResponse | null>(null);
    let loadingUsage = $state(true);
    let clearingUsage = $state(false);

    async function loadUsage() {
        try {
            usage = await fetchAiUsage('30d');
        } catch (e) {
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
</script>

<div class="space-y-6">
    <!-- Usage Dashboard -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center justify-between mb-8">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-indigo-500/10 flex items-center justify-center text-indigo-600 dark:text-indigo-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" /></svg>
                </div>
                <div>
                    <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.ai.usage_title', { default: 'AI Usage' })}</h3>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{$_('settings.ai.usage_subtitle', { default: 'Last 30 days consumption' })}</p>
                </div>
            </div>
            <button
                onclick={handleClearUsage}
                disabled={clearingUsage || !usage?.calls}
                class="px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 text-[10px] font-black uppercase tracking-widest hover:bg-red-50 dark:hover:bg-red-900/20 hover:text-red-600 transition-all disabled:opacity-50"
            >
                {clearingUsage ? $_('common.clearing', { default: 'Clearing...' }) : $_('settings.ai.clear_usage', { default: 'Clear History' })}
            </button>
        </div>

        {#if loadingUsage}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 animate-pulse">
                <div class="h-24 rounded-2xl bg-slate-100 dark:bg-slate-800/50"></div>
                <div class="h-24 rounded-2xl bg-slate-100 dark:bg-slate-800/50"></div>
                <div class="h-24 rounded-2xl bg-slate-100 dark:bg-slate-800/50"></div>
            </div>
        {:else if usage}
            <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
                <div class="p-6 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/50">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">{$_('settings.ai.total_calls', { default: 'API Requests' })}</p>
                    <p class="text-2xl font-black text-slate-900 dark:text-white">{usage.calls.toLocaleString()}</p>
                </div>
                <div class="p-6 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/50">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mb-1">{$_('settings.ai.total_tokens', { default: 'Tokens Consumed' })}</p>
                    <p class="text-2xl font-black text-slate-900 dark:text-white">{formatTokens(usage.total_tokens)}</p>
                    <p class="text-[9px] font-bold text-slate-400 mt-1">{formatTokens(usage.input_tokens)} in / {formatTokens(usage.output_tokens)} out</p>
                </div>
                <div class="p-6 rounded-2xl bg-emerald-500/5 dark:bg-emerald-500/10 border border-emerald-500/10 dark:border-emerald-500/20">
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
                <div class="overflow-hidden rounded-2xl border border-slate-100 dark:border-slate-800/50">
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
                        <tbody class="divide-y divide-slate-100 dark:divide-slate-800/50">
                            {#each usage.breakdown as item}
                                <tr class="text-slate-700 dark:text-slate-300">
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
            <div class="p-12 text-center rounded-2xl border-2 border-dashed border-slate-200 dark:border-slate-800">
                <p class="text-sm font-bold text-slate-400">{$_('settings.ai.no_usage_data', { default: 'No AI usage recorded yet.' })}</p>
            </div>
        {/if}
    </section>

    <!-- Connection -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-8">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
                </div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.ai.connection_title', { default: 'Model Configuration' })}</h3>
            </div>
            <div class="flex items-center gap-2">
                <button
                    role="switch"
                    aria-checked={llmEnabled}
                    onclick={() => llmEnabled = !llmEnabled}
                    class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {llmEnabled ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                >
                    <span class="sr-only">{$_('settings.llm.enabled')}</span>
                    <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {llmEnabled ? 'translate-x-5' : 'translate-x-0'}"></span>
                </button>
            </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div class="space-y-6">
                <div>
                    <span class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.llm.provider')}</span>
                    <div class="grid grid-cols-3 gap-2">
                        {#each ['gemini', 'openai', 'claude'] as provider}
                            <button
                                onclick={() => llmProvider = provider}
                                class="px-4 py-3 rounded-2xl border-2 transition-all font-black text-[10px] uppercase tracking-widest {llmProvider === provider ? 'border-teal-500 bg-teal-500/5 text-teal-600 dark:text-teal-400' : 'border-slate-100 dark:border-slate-800 text-slate-400 hover:border-teal-500/20'}"
                            >
                                {provider}
                            </button>
                        {/each}
                    </div>
                </div>

                <div>
                    <label for="llm-api-key" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.llm.api_key')}</label>
                    <div class="relative">
                        <input
                            id="llm-api-key"
                            type="password"
                            bind:value={llmApiKey}
                            placeholder={llmApiKeySaved ? '***REDACTED***' : 'sk-...'}
                            class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-mono text-xs focus:ring-2 focus:ring-teal-500 outline-none"
                        />
                        {#if llmApiKeySaved && !llmApiKey}
                            <div class="absolute inset-y-0 right-4 flex items-center">
                                <span class="px-2 py-0.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[9px] font-black rounded uppercase">{$_('settings.common.saved', { default: 'Saved' })}</span>
                            </div>
                        {/if}
                    </div>
                </div>

                <div>
                    <label for="llm-model" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.llm.model')}</label>
                    <input
                        id="llm-model"
                        type="text"
                        bind:value={llmModel}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none"
                    />
                    <p class="mt-2 text-[9px] text-slate-400 font-bold italic">
                        {llmProvider === 'gemini' ? 'Recommended: gemini-1.5-flash' : llmProvider === 'openai' ? 'Recommended: gpt-4o-mini' : 'Recommended: claude-3-haiku-20240307'}
                    </p>
                </div>

                <div class="pt-2">
                    <button
                        onclick={onTestConnection}
                        disabled={!llmApiKey && !llmApiKeySaved}
                        class="w-full px-6 py-3 bg-slate-900 dark:bg-slate-700 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-800 transition-all disabled:opacity-50"
                    >
                        {$_('settings.llm.test_connection')}
                    </button>
                </div>
            </div>

            <div class="p-6 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/50 flex flex-col justify-center">
                <div class="flex items-start gap-4">
                    <div class="w-12 h-12 rounded-2xl bg-blue-500/10 flex items-center justify-center text-blue-600 dark:text-blue-400 flex-shrink-0">
                        <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                    </div>
                    <div>
                        <h4 class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.ai.provider_info_title', { default: 'Cloud AI Providers' })}</h4>
                        <p class="text-xs font-bold text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
                            {$_('settings.ai.provider_info_desc', { default: 'YA-WAMF uses cloud LLMs for behavioral analysis and natural language interactions. You will need your own API key from the provider.' })}
                        </p>
                        <div class="mt-4 space-y-2">
                            <a href="https://aistudio.google.com/app/apikey" target="_blank" rel="noopener noreferrer" class="block text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline uppercase tracking-widest">Get Google Gemini Key →</a>
                            <a href="https://platform.openai.com/api-keys" target="_blank" rel="noopener noreferrer" class="block text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline uppercase tracking-widest">Get OpenAI Key →</a>
                            <a href="https://console.anthropic.com/" target="_blank" rel="noopener noreferrer" class="block text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline uppercase tracking-widest">Get Anthropic Claude Key →</a>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Pricing Configuration -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center gap-3 mb-8">
            <div class="w-10 h-10 rounded-2xl bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
            <div>
                <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.ai.pricing_title', { default: 'Cost Estimation' })}</h3>
                <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{$_('settings.ai.pricing_subtitle', { default: 'Configure costs per 1M tokens' })}</p>
            </div>
        </div>

        <div class="space-y-4">
            <div class="flex items-center justify-between">
                <label for="ai-pricing-json" class="block text-[10px] font-black uppercase tracking-widest text-slate-500">{$_('settings.ai.pricing_json', { default: 'Pricing Registry (JSON)' })}</label>
                <a href="/docs/ai-pricing.json" target="_blank" class="text-[10px] font-black text-teal-600 dark:text-teal-400 hover:underline uppercase tracking-widest">View Reference Pricing →</a>
            </div>
            <textarea
                id="ai-pricing-json"
                bind:value={aiPricingJson}
                rows="8"
                class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-mono text-xs focus:ring-2 focus:ring-teal-500 outline-none"
                placeholder={'[{"provider": "gemini", "model": "*", "inputPer1M": 0.3, "outputPer1M": 2.5}]'}
            ></textarea>
            <p class="text-[10px] font-bold text-slate-500 leading-relaxed">
                {$_('settings.ai.pricing_help', { default: 'Override the default token pricing for cost estimation. Format: an array of objects with provider, model, inputPer1M, and outputPer1M.' })}
            </p>
        </div>
    </section>

    <!-- Prompts -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-8">
            <div class="flex items-center gap-3">
                <div class="w-10 h-10 rounded-2xl bg-amber-500/10 flex items-center justify-center text-amber-600 dark:text-amber-400">
                    <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" /></svg>
                </div>
                <div>
                    <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.ai.prompts_title', { default: 'Prompt Templates' })}</h3>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 mt-1">{$_('settings.ai.prompts_subtitle', { default: 'Customize the behavior of AI features' })}</p>
                </div>
            </div>
        </div>

        <div class="space-y-8">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6 p-6 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-800/50">
                <div>
                    <label for="llm-prompt-style" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.debug.llm_prompt_style_label')}</label>
                    <select
                        id="llm-prompt-style"
                        bind:value={llmPromptStyle}
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-white font-bold text-sm outline-none"
                    >
                        <option value="classic">{$_('settings.debug.llm_prompt_style_classic')}</option>
                        <option value="field">{$_('settings.debug.llm_prompt_style_field')}</option>
                    </select>
                </div>
                <div class="flex items-end gap-2">
                    <button
                        onclick={onApplyStyle}
                        class="flex-1 px-6 py-3 bg-slate-900 dark:bg-slate-700 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-800 transition-all"
                    >
                        {$_('settings.debug.llm_prompt_apply_style')}
                    </button>
                    <button
                        onclick={onResetDefaults}
                        class="flex-1 px-6 py-3 border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-all"
                    >
                        {$_('settings.debug.llm_prompt_reset_defaults')}
                    </button>
                </div>
            </div>

            <div class="space-y-6">
                <div>
                    <label for="llm-prompt-analysis" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.debug.llm_prompt_analysis')}</label>
                    <textarea
                        id="llm-prompt-analysis"
                        bind:value={llmAnalysisPromptTemplate}
                        rows="6"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-mono text-xs focus:ring-2 focus:ring-amber-500 outline-none"
                    ></textarea>
                    <p class="mt-2 text-[9px] font-bold text-slate-400">{$_('settings.debug.llm_prompt_analysis_hint')}</p>
                </div>

                <div>
                    <label for="llm-prompt-conversation" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.debug.llm_prompt_conversation')}</label>
                    <textarea
                        id="llm-prompt-conversation"
                        bind:value={llmConversationPromptTemplate}
                        rows="6"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-mono text-xs focus:ring-2 focus:ring-amber-500 outline-none"
                    ></textarea>
                    <p class="mt-2 text-[9px] font-bold text-slate-400">{$_('settings.debug.llm_prompt_conversation_hint')}</p>
                </div>

                <div>
                    <label for="llm-prompt-chart" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.debug.llm_prompt_chart')}</label>
                    <textarea
                        id="llm-prompt-chart"
                        bind:value={llmChartPromptTemplate}
                        rows="6"
                        class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-mono text-xs focus:ring-2 focus:ring-amber-500 outline-none"
                    ></textarea>
                    <p class="mt-2 text-[9px] font-bold text-slate-400">{$_('settings.debug.llm_prompt_chart_hint')}</p>
                </div>
            </div>
        </div>
    </section>
</div>
