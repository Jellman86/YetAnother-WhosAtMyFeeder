<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { formatDateTime } from '../../utils/datetime';
    import ModelManager from '../../pages/models/ModelManager.svelte';

    // Props
    let {
        threshold = $bindable(0.7),
        minConfidence = $bindable(0.4),
        trustFrigateSublabel = $bindable(true),
        displayCommonNames = $bindable(true),
        scientificNamePrimary = $bindable(false),
        autoVideoClassification = $bindable(false),
        videoClassificationDelay = $bindable(30),
        videoClassificationMaxRetries = $bindable(3),
        videoCircuitOpen = false,
        videoCircuitUntil = null,
        videoCircuitFailures = 0,
        blockedLabels = $bindable<string[]>([]),
        newBlockedLabel = $bindable(''),
        addBlockedLabel,
        removeBlockedLabel
    }: {
        threshold: number;
        minConfidence: number;
        trustFrigateSublabel: boolean;
        displayCommonNames: boolean;
        scientificNamePrimary: boolean;
        autoVideoClassification: boolean;
        videoClassificationDelay: number;
        videoClassificationMaxRetries: number;
        videoCircuitOpen: boolean;
        videoCircuitUntil: string | null;
        videoCircuitFailures: number;
        blockedLabels: string[];
        newBlockedLabel: string;
        addBlockedLabel: () => void;
        removeBlockedLabel: (label: string) => void;
    } = $props();

    const circuitUntil = $derived(videoCircuitUntil ? formatDateTime(videoCircuitUntil) : null);
</script>

<div class="space-y-6">
    <!-- Classification Model -->
    <section class="card-base rounded-3xl p-8 backdrop-blur-md">
        <div class="flex items-center gap-3 mb-8">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">{$_('settings.detection.classification_engine')}</h3>
        </div>
        <ModelManager />
    </section>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Tuning -->
        <section class="card-base rounded-3xl p-8">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">{$_('settings.detection.fine_tuning')}</h4>

            <div class="space-y-8">
                <div>
                    <div class="flex justify-between mb-4">
                        <label for="confidence-threshold-slider" class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.confidence_threshold')}</label>
                        <output for="confidence-threshold-slider" class="px-2 py-1 bg-teal-500 text-white text-[10px] font-black rounded-lg">{(threshold * 100).toFixed(0)}%</output>
                    </div>
                    <input
                        id="confidence-threshold-slider"
                        type="range"
                        min="0"
                        max="1"
                        step="0.05"
                        bind:value={threshold}
                                            aria-valuemin="0"
                                            aria-valuemax="100"
                                            aria-valuenow={Math.round(threshold * 100)}
                                            aria-valuetext="{(threshold * 100).toFixed(0)} percent"
                                            aria-label="{$_('settings.detection.confidence_threshold')}: {(threshold * 100).toFixed(0)}%"
                                            class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-teal-500"
                                        />
                                        <div class="flex justify-between mt-2"><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.threshold_loose')}</span><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.threshold_strict')}</span></div>
                                    </div>
                        
                                        <div>
                                            <div class="flex justify-between mb-4">
                                                <label for="min-confidence-slider" class="text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.min_confidence_floor')}</label>
                                                <output for="min-confidence-slider" class="px-2 py-1 bg-amber-500 text-white text-[10px] font-black rounded-lg">{(minConfidence * 100).toFixed(0)}%</output>
                                            </div>
                                            <input
                                                id="min-confidence-slider"
                                                type="range"
                                                min="0"
                                                max="1"
                                                step="0.05"
                                                bind:value={minConfidence}
                                                aria-valuemin="0"
                                                aria-valuemax="100"
                                                aria-valuenow={Math.round(minConfidence * 100)}
                                                aria-valuetext="{(minConfidence * 100).toFixed(0)} percent"
                                                aria-label="{$_('settings.detection.min_confidence_floor')}: {(minConfidence * 100).toFixed(0)}%"
                                                aria-describedby="min-confidence-help"
                                                class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-amber-500"
                                            />
                                            <div class="flex justify-between mt-2">
                                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.floor_capture_all')}</span>
                                                <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">{$_('settings.detection.floor_reject_unsure')}</span>
                                            </div>
                                            <p id="min-confidence-help" class="mt-3 text-[10px] text-slate-500 font-bold leading-tight">{$_('settings.detection.floor_help')}</p>
                                        </div>
                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 flex items-center justify-between gap-4">
                    <div id="trust-frigate-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.trust_frigate')}</span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.detection.trust_frigate_desc')}</span>
                    </div>
                    <button
                        role="switch"
                        aria-checked={trustFrigateSublabel}
                        aria-labelledby="trust-frigate-label"
                        onclick={() => trustFrigateSublabel = !trustFrigateSublabel}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                trustFrigateSublabel = !trustFrigateSublabel;
                            }
                        }}
                        class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {trustFrigateSublabel ? 'bg-teal-500' : 'bg-slate-300 dark:bg-slate-600'}"
                    >
                        <span class="sr-only">{$_('settings.detection.trust_frigate')}</span>
                        <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {trustFrigateSublabel ? 'translate-x-5' : 'translate-x-0'}"></span>
                    </button>
                </div>

                <div class="space-y-4 pt-4 border-t border-slate-100 dark:border-slate-700/50">
                    <div class="flex items-center justify-between">
                        <div id="auto-video-label">
                            <span class="block text-sm font-black text-slate-900 dark:text-white">{$_('settings.detection.auto_video')}</span>
                            <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">{$_('settings.detection.auto_video_desc')}</span>
                        </div>
                        <button
                            role="switch"
                            aria-checked={autoVideoClassification}
                            aria-labelledby="auto-video-label"
                            onclick={() => autoVideoClassification = !autoVideoClassification}
                            onkeydown={(e) => {
                                if (e.key === 'Enter' || e.key === ' ') {
                                    e.preventDefault();
                                    autoVideoClassification = !autoVideoClassification;
                                }
                            }}
                            class="relative inline-flex h-6 w-11 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 focus:outline-none {autoVideoClassification ? 'bg-indigo-500' : 'bg-slate-300 dark:bg-slate-600'}"
                        >
                            <span class="sr-only">{$_('settings.detection.auto_video')}</span>
                            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {autoVideoClassification ? 'translate-x-5' : 'translate-x-0'}"></span>
                        </button>
                    </div>

                    {#if autoVideoClassification}
                        {#if videoCircuitOpen}
                            <div role="alert" class="p-4 rounded-2xl bg-amber-500/10 border border-amber-500/20 text-slate-700 dark:text-slate-200">
                                <p class="text-[10px] font-black uppercase tracking-[0.2em] text-amber-600 dark:text-amber-400 mb-2">
                                    {$_('settings.video_circuit.title')}
                                </p>
                                <p class="text-xs font-bold leading-relaxed">
                                    {$_('settings.video_circuit.message', { values: { failures: videoCircuitFailures } })}
                                </p>
                                {#if circuitUntil}
                                    <p class="text-[10px] text-slate-500 mt-2">
                                        {$_('settings.video_circuit.until', { values: { time: circuitUntil } })}
                                    </p>
                                {/if}
                            </div>
                        {/if}
                        <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                            <div>
                                <label for="video-delay" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.detection.video_delay')}</label>
                                <input
                                    id="video-delay"
                                    type="number"
                                    bind:value={videoClassificationDelay}
                                    min="0"
                                    aria-label={$_('settings.detection.video_delay')}
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                            <div>
                                <label for="video-retries" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">{$_('settings.detection.video_retries')}</label>
                                <input
                                    id="video-retries"
                                    type="number"
                                    bind:value={videoClassificationMaxRetries}
                                    min="0"
                                    aria-label={$_('settings.detection.video_retries')}
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                        </div>
                        <p class="text-[9px] text-slate-400 italic">{$_('settings.detection.video_retry_note')}</p>
                    {/if}
                </div>
            </div>
        </section>

        <!-- Naming -->
        <section class="card-base rounded-3xl p-8">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">{$_('settings.detection.naming_title')}</h4>

            <div class="flex flex-col gap-3">
                {#each [
                    { id: 'standard', title: $_('settings.detection.naming_standard'), sub: $_('settings.detection.naming_standard_sub'), active: displayCommonNames && !scientificNamePrimary, action: () => { displayCommonNames = true; scientificNamePrimary = false; } },
                    { id: 'hobbyist', title: $_('settings.detection.naming_hobbyist'), sub: $_('settings.detection.naming_hobbyist_sub'), active: displayCommonNames && scientificNamePrimary, action: () => { displayCommonNames = true; scientificNamePrimary = true; } },
                    { id: 'scientific', title: $_('settings.detection.naming_scientific'), sub: $_('settings.detection.naming_scientific_sub'), active: !displayCommonNames, action: () => { displayCommonNames = false; } }
                ] as mode}
                    <button
                        onclick={mode.action}
                        aria-label="{$_('common.refresh') === 'Refresh' ? 'Select' : 'Auswählen'} {mode.title} {$_('settings.detection.naming_title') === 'Bird Naming Style' ? 'naming style' : 'Benennungsstil'}"
                        class="flex items-center gap-4 p-4 rounded-2xl border-2 text-left transition-all {mode.active ? 'border-teal-500 bg-teal-500/5' : 'border-slate-100 dark:border-slate-700/50 hover:border-teal-500/20'}"
                    >
                        <div class="w-5 h-5 rounded-full border-2 flex items-center justify-center {mode.active ? 'border-teal-500 bg-teal-500' : 'border-slate-300 dark:border-slate-600'}">
                            {#if mode.active}<svg class="w-4 h-4 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="4" d="M5 13l4 4L19 7" /></svg>{/if}
                        </div>
                        <div>
                            <p class="text-sm font-black text-slate-900 dark:text-white leading-none">{mode.title}</p>
                            <p class="text-[10px] font-bold text-slate-500 mt-1">{mode.sub}</p>
                        </div>
                    </button>
                {/each}
            </div>
        </section>
    </div>

    <!-- Blocked Labels -->
    <section class="card-base rounded-3xl p-8">
        <div class="flex items-center justify-between mb-6">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">{$_('settings.detection.blocked_labels')}</h4>
            <span class="px-2 py-0.5 bg-red-500/10 text-red-500 text-[9px] font-black rounded uppercase">{$_('settings.detection.ignored_by_discovery')}</span>
        </div>

        <div class="flex gap-2 mb-6">
            <input
                bind:value={newBlockedLabel}
                onkeydown={(e) => e.key === 'Enter' && addBlockedLabel()}
                placeholder="e.g. background"
                aria-label={$_('settings.detection.blocked_labels')}
                class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
            />
            <button
                onclick={addBlockedLabel}
                disabled={!newBlockedLabel.trim()}
                aria-label="{$_('common.add')} {$_('settings.detection.blocked_labels')}"
                class="px-6 py-3 bg-slate-900 dark:bg-slate-700 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-800 transition-all disabled:opacity-50"
            >
                {$_('common.add')}
            </button>
        </div>

        <div class="flex flex-wrap gap-2">
            {#each blockedLabels as label}
                <span class="group flex items-center gap-2 px-3 py-1.5 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl text-xs font-bold text-slate-700 dark:text-slate-300">
                    {label}
                    <button
                        onclick={() => removeBlockedLabel(label)}
                        aria-label="Remove {label} from blocked list"
                        class="text-slate-400 hover:text-red-500 transition-colors"
                    >
                        ✕
                    </button>
                </span>
            {/each}
            {#if blockedLabels.length === 0}<p class="text-xs font-bold text-slate-400 italic">{$_('settings.detection.no_blocked_labels')}</p>{/if}
        </div>
    </section>
</div>
