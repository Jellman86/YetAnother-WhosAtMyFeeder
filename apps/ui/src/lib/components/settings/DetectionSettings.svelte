<script lang="ts">
    import { _ } from 'svelte-i18n';
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
        blockedLabels: string[];
        newBlockedLabel: string;
        addBlockedLabel: () => void;
        removeBlockedLabel: (label: string) => void;
    } = $props();
</script>

<div class="space-y-6">
    <!-- Classification Model -->
    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm backdrop-blur-md">
        <div class="flex items-center gap-3 mb-8">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" /></svg>
            </div>
            <h3 class="text-xl font-black text-slate-900 dark:text-white tracking-tight">Classification Engine</h3>
        </div>
        <ModelManager />
    </section>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Tuning -->
        <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">Fine Tuning</h4>

            <div class="space-y-8">
                <div>
                    <div class="flex justify-between mb-4">
                        <label for="confidence-threshold-slider" class="text-sm font-black text-slate-900 dark:text-white">Confidence Threshold</label>
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
                        aria-valuenow={(threshold * 100).toFixed(0)}
                        aria-valuetext="{(threshold * 100).toFixed(0)} percent"
                        aria-label="Confidence threshold: {(threshold * 100).toFixed(0)}%"
                        class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-teal-500"
                    />
                    <div class="flex justify-between mt-2"><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Loose</span><span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Strict</span></div>
                </div>

                <div>
                    <div class="flex justify-between mb-4">
                        <label for="min-confidence-slider" class="text-sm font-black text-slate-900 dark:text-white">Minimum Confidence Floor</label>
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
                        aria-valuenow={(minConfidence * 100).toFixed(0)}
                        aria-valuetext="{(minConfidence * 100).toFixed(0)} percent"
                        aria-label="Minimum confidence floor: {(minConfidence * 100).toFixed(0)}%"
                        aria-describedby="min-confidence-help"
                        class="w-full h-2 rounded-lg bg-slate-200 dark:bg-slate-700 appearance-none cursor-pointer accent-amber-500"
                    />
                    <div class="flex justify-between mt-2">
                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Capture All</span>
                        <span class="text-[9px] font-bold text-slate-400 uppercase tracking-tighter">Reject Unsure</span>
                    </div>
                    <p id="min-confidence-help" class="mt-3 text-[10px] text-slate-500 font-bold leading-tight">Events below this floor are ignored completely. Events between floor and threshold are saved as "Unknown Bird".</p>
                </div>

                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 flex items-center justify-between gap-4">
                    <div id="trust-frigate-label" class="flex-1">
                        <span class="block text-sm font-black text-slate-900 dark:text-white">Trust Frigate Sublabels</span>
                        <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">Skip internal classification if Frigate identified species</span>
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
                        <span class="sr-only">Trust Frigate Sublabels</span>
                        <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {trustFrigateSublabel ? 'translate-x-5' : 'translate-x-0'}"></span>
                    </button>
                </div>

                <div class="space-y-4 pt-4 border-t border-slate-100 dark:border-slate-700/50">
                    <div class="flex items-center justify-between">
                        <div id="auto-video-label">
                            <span class="block text-sm font-black text-slate-900 dark:text-white">Auto Video Analysis</span>
                            <span class="block text-[10px] text-slate-500 font-bold leading-tight mt-1">Automatically run deep video reclassification for every event</span>
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
                            <span class="sr-only">Auto Video Analysis</span>
                            <span class="pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow transition duration-200 {autoVideoClassification ? 'translate-x-5' : 'translate-x-0'}"></span>
                        </button>
                    </div>

                    {#if autoVideoClassification}
                        <div class="grid grid-cols-2 gap-4 animate-in fade-in slide-in-from-top-2">
                            <div>
                                <label for="video-delay" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Initial Delay (s)</label>
                                <input
                                    id="video-delay"
                                    type="number"
                                    bind:value={videoClassificationDelay}
                                    min="0"
                                    aria-label="Initial delay in seconds"
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                            <div>
                                <label for="video-retries" class="block text-[10px] font-black uppercase tracking-widest text-slate-500 mb-2">Max Retries</label>
                                <input
                                    id="video-retries"
                                    type="number"
                                    bind:value={videoClassificationMaxRetries}
                                    min="0"
                                    aria-label="Maximum retries"
                                    class="w-full px-4 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-xs focus:ring-2 focus:ring-indigo-500 outline-none"
                                />
                            </div>
                        </div>
                        <p class="text-[9px] text-slate-400 italic">Retries use exponential backoff to wait for Frigate clip finalization.</p>
                    {/if}
                </div>
            </div>
        </section>

        <!-- Naming -->
        <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400 mb-6">Bird Naming Style</h4>

            <div class="flex flex-col gap-3">
                {#each [
                    { id: 'standard', title: 'Standard', sub: 'Common names primary, scientific subtitles.', active: displayCommonNames && !scientificNamePrimary, action: () => { displayCommonNames = true; scientificNamePrimary = false; } },
                    { id: 'hobbyist', title: 'Hobbyist', sub: 'Scientific names primary, common subtitles.', active: displayCommonNames && scientificNamePrimary, action: () => { displayCommonNames = true; scientificNamePrimary = true; } },
                    { id: 'scientific', title: 'Strictly Scientific', sub: 'Only show scientific names. Hides common names.', active: !displayCommonNames, action: () => { displayCommonNames = false; } }
                ] as mode}
                    <button
                        onclick={mode.action}
                        aria-label="Select {mode.title} naming style"
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
    <section class="bg-white dark:bg-slate-800/50 rounded-3xl border border-slate-200/80 dark:border-slate-700/50 p-8 shadow-sm">
        <div class="flex items-center justify-between mb-6">
            <h4 class="text-xs font-black uppercase tracking-[0.2em] text-slate-400">Blocked Labels</h4>
            <span class="px-2 py-0.5 bg-red-500/10 text-red-500 text-[9px] font-black rounded uppercase">Ignored by Discovery</span>
        </div>

        <div class="flex gap-2 mb-6">
            <input
                bind:value={newBlockedLabel}
                onkeydown={(e) => e.key === 'Enter' && addBlockedLabel()}
                placeholder="e.g. background"
                aria-label="New blocked label"
                class="flex-1 px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm"
            />
            <button
                onclick={addBlockedLabel}
                disabled={!newBlockedLabel.trim()}
                aria-label="Add blocked label"
                class="px-6 py-3 bg-slate-900 dark:bg-slate-700 text-white text-xs font-black uppercase tracking-widest rounded-2xl hover:bg-slate-800 transition-all disabled:opacity-50"
            >
                Add
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
            {#if blockedLabels.length === 0}<p class="text-xs font-bold text-slate-400 italic">No labels blocked yet.</p>{/if}
        </div>
    </section>
</div>
