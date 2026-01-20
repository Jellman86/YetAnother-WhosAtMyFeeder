<script lang="ts">
    import { getThumbnailUrl, analyzeDetection, updateDetectionSpecies, hideDetection, deleteDetection, searchSpecies, type SearchResult } from '../api';
    import type { Detection } from '../api';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import { detectionsStore, type ReclassificationProgress } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { getBirdNames } from '../naming';
    import { _ } from 'svelte-i18n';
    import { trapFocus } from '../utils/focus-trap';
    import { formatTemperature } from '../utils/temperature';

    interface Props {
        detection: Detection;
        classifierLabels: string[];
        llmEnabled: boolean;
        showVideoButton?: boolean;
        onClose: () => void;
        onReclassify: (detection: Detection) => void;
        onPlayVideo?: () => void;
        onViewSpecies: (speciesName: string) => void;
    }

    let {
        detection,
        classifierLabels,
        llmEnabled,
        showVideoButton = false,
        onClose,
        onReclassify,
        onPlayVideo,
        onViewSpecies
    }: Props = $props();

    // State
    let modalElement = $state<HTMLElement | null>(null);
    let analyzingAI = $state(false);

    $effect(() => {
        if (modalElement) {
            return trapFocus(modalElement);
        }
    });

    let aiAnalysis = $state<string | null>(null);
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);
    let tagSearchQuery = $state('');
    let searchResults = $state<SearchResult[]>([]);
    let isSearching = $state(false);

    // Reclassification progress
    let reclassifyProgress = $derived(
        detectionsStore.progressMap.get(detection.frigate_event) || null
    );

    // Naming logic
    const showCommon = $derived(settingsStore.settings?.display_common_names ?? true);
    const preferSci = $derived(settingsStore.settings?.scientific_name_primary ?? false);
    const naming = $derived(getBirdNames(detection, showCommon, preferSci));
    const primaryName = $derived(naming.primary);
    const subName = $derived(naming.secondary);

    // Handle search input
    let searchTimeout: any;
    $effect(() => {
        const query = tagSearchQuery.trim();
        if (query.length === 0) {
            clearTimeout(searchTimeout);
            isSearching = true;
            (async () => {
                try {
                    searchResults = await searchSpecies('', 20);
                } catch (e) {
                    console.error("Search failed", e);
                    searchResults = classifierLabels.slice(0, 20).map(l => ({
                        id: l, display_name: l, common_name: null, scientific_name: null
                    }));
                } finally {
                    isSearching = false;
                }
            })();
            return;
        }

        clearTimeout(searchTimeout);
        searchTimeout = setTimeout(async () => {
            isSearching = true;
            try {
                // Use backend search for rich taxonomy results
                searchResults = await searchSpecies(query);
            } catch (e) {
                console.error("Search failed", e);
                // Fallback to local filtering
                searchResults = classifierLabels
                    .filter(l => l.toLowerCase().includes(query.toLowerCase()))
                    .map(l => ({ id: l, display_name: l, common_name: null, scientific_name: null }));
            } finally {
                isSearching = false;
            }
        }, 300);
    });

    function getResultNames(result: SearchResult) {
        const common = result.common_name?.trim() || null;
        const scientific = result.scientific_name?.trim() || null;
        const fallback = result.display_name || result.id;

        if (common && scientific && common !== scientific) {
            return { primary: common, secondary: scientific };
        }

        return { primary: common || scientific || fallback, secondary: null };
    }

    function getVideoFailureMessage(error: string | null | undefined) {
        if (!error) {
            return $_('detection.video_analysis.errors.unknown');
        }
        if (error.startsWith('clip_http_')) {
            return $_('detection.video_analysis.errors.clip_unavailable');
        }
        if (error.startsWith('event_http_')) {
            return $_('detection.video_analysis.errors.frigate_unavailable');
        }

        switch (error) {
            case 'clip_unavailable':
            case 'clip_not_found':
                return $_('detection.video_analysis.errors.clip_unavailable');
            case 'clip_timeout':
            case 'event_timeout':
                return $_('detection.video_analysis.errors.timeout');
            case 'clip_request_error':
            case 'event_request_error':
                return $_('detection.video_analysis.errors.frigate_unavailable');
            case 'clip_invalid':
                return $_('detection.video_analysis.errors.clip_invalid');
            case 'clip_decode_failed':
                return $_('detection.video_analysis.errors.clip_decode_failed');
            case 'video_no_results':
                return $_('detection.video_analysis.errors.no_results');
            case 'event_not_found':
                return $_('detection.video_analysis.errors.event_missing');
            default:
                return $_('detection.video_analysis.errors.unknown');
        }
    }

    async function handleAIAnalysis(force: boolean = false) {
        if (!detection) return;
        analyzingAI = true;
        if (force) {
            aiAnalysis = null; // Clear existing analysis when forcing regeneration
        }

        try {
            const result = await analyzeDetection(detection.frigate_event, force);
            aiAnalysis = result.analysis;
        } catch (e: any) {
            aiAnalysis = $_('detection.ai.error', { values: { message: e.message || 'Analysis failed' } });
        } finally {
            analyzingAI = false;
        }
    }

    async function handleManualTag(newSpecies: string) {
        if (!detection) return;
        updatingTag = true;
        try {
            await updateDetectionSpecies(detection.frigate_event, newSpecies);
            detection.display_name = newSpecies;
            detectionsStore.updateDetection({ ...detection, display_name: newSpecies });
            showTagDropdown = false;
            aiAnalysis = null; // Reset AI analysis for new species
        } catch (e: any) {
            alert($_('notifications.reclassify_failed', { values: { message: e.message } }));
        } finally {
            updatingTag = false;
        }
    }

    async function handleHide() {
        if (!detection) return;
        try {
            const result = await hideDetection(detection.frigate_event);
            if (result.is_hidden) {
                detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
                onClose();
            }
        } catch (e: any) {
            alert($_('notifications.reclassify_failed', { values: { message: e.message } }));
        }
    }

    async function handleDelete() {
        if (!detection) return;
        if (!confirm($_('actions.confirm_delete', { values: { species: detection.display_name } }))) return;

        try {
            await deleteDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            onClose();
        } catch (e: any) {
            alert($_('notifications.reclassify_failed', { values: { message: e.message } }));
        }
    }

    function handleReclassifyClick() {
        onReclassify(detection);
    }

    function handleSpeciesInfo() {
        onViewSpecies(detection.display_name);
        onClose();
    }
</script>

<div
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
    onclick={onClose}
    onkeydown={(e) => e.key === 'Escape' && onClose()}
    role="dialog"
    aria-modal="true"
    tabindex="-1"
>
    <div
        bind:this={modalElement}
        class="relative bg-white dark:bg-slate-800 rounded-3xl shadow-2xl max-w-lg w-full max-h-[90vh] flex flex-col border border-white/20 overflow-hidden"
        onclick={(e) => e.stopPropagation()}
        onkeydown={(e) => e.stopPropagation()}
        role="document"
        tabindex="-1"
    >

        <!-- Reclassification Overlay (covers entire modal content) -->
        {#if reclassifyProgress}
            <ReclassificationOverlay progress={reclassifyProgress} />
        {/if}

        <div class="relative aspect-video bg-slate-100 dark:bg-slate-700">
            <img src={getThumbnailUrl(detection.frigate_event)} alt={detection.display_name} class="w-full h-full object-cover" />
            <div class="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-transparent"></div>
            <div class="absolute bottom-0 left-0 right-0 p-6">
                <h3 class="text-2xl font-black text-white drop-shadow-lg leading-tight">{primaryName}</h3>
                {#if subName && subName !== primaryName}
                    <p class="text-white/70 text-sm italic drop-shadow -mt-1 mb-1">{subName}</p>
                {/if}
                <p class="text-white/50 text-[10px] uppercase font-bold tracking-widest mt-2">
                    {new Date(detection.detection_time).toLocaleString()}
                </p>
            </div>

            <!-- Video Play Button (optional) -->
            {#if showVideoButton && detection.has_clip && onPlayVideo}
                <button
                    type="button"
                    onclick={onPlayVideo}
                    class="absolute inset-0 flex items-center justify-center bg-black/0 hover:bg-black/20 transition-all group/play focus:outline-none"
                >
                    <div class="w-16 h-16 rounded-full bg-white/90 dark:bg-slate-800/90 flex items-center justify-center shadow-lg opacity-70 group-hover/play:opacity-100 transform scale-90 group-hover/play:scale-100 transition-all duration-200">
                        <svg xmlns="http://www.w3.org/2000/svg" class="w-7 h-7 text-teal-600 dark:text-teal-400 ml-1" viewBox="0 0 24 24" fill="currentColor">
                            <path d="M8 5v14l11-7z"/>
                        </svg>
                    </div>
                </button>
            {/if}

            <button
                onclick={onClose}
                class="absolute top-4 right-4 w-8 h-8 rounded-full bg-black/40 text-white flex items-center justify-center hover:bg-black/60 transition-colors"
                aria-label="Close"
            >
                <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>

        <div class="flex-1 overflow-y-auto p-6 space-y-6 {showTagDropdown ? 'blur-sm pointer-events-none select-none' : ''}">
            <!-- Confidence Bar -->
            {#if !detection.manual_tagged}
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{$_('detection.confidence')}</span>
                        <span class="text-sm font-black text-slate-900 dark:text-white">
                            {((detection.score || 0) * 100).toFixed(1)}%
                        </span>
                    </div>
                    <div class="h-2 bg-slate-100 dark:bg-slate-700 rounded-full overflow-hidden">
                        <div
                            class="h-full rounded-full transition-all duration-700 {(detection.score || 0) >= 0.8 ? 'bg-emerald-500' : 'bg-teal-500'}"
                            style="width: {(detection.score || 0) * 100}%"
                        ></div>
                    </div>
                </div>
            {/if}

            <!-- Video Classification Results -->
            {#if detection.video_classification_status === 'completed' || (detection.video_classification_label && detection.video_classification_label !== detection.display_name)}
                <div class="p-4 rounded-2xl bg-indigo-50/80 dark:bg-indigo-500/10 border border-indigo-200/80 dark:border-indigo-500/20 animate-in fade-in slide-in-from-top-2">
                    <div class="flex items-center justify-between mb-2">
                        <p class="text-[10px] font-black text-indigo-600 dark:text-indigo-400 uppercase tracking-[0.2em]">
                            {$_('detection.video_analysis.title')}
                        </p>
                        {#if detection.video_classification_score}
                            <span class="px-2 py-0.5 bg-indigo-500 text-white text-[9px] font-black rounded uppercase">
                                {$_('detection.video_analysis.match', { values: { score: (detection.video_classification_score * 100).toFixed(0) } })}
                            </span>
                        {/if}
                    </div>
                    <p class="text-sm font-bold text-slate-800 dark:text-slate-200">
                        {detection.video_classification_label}
                    </p>
                    <p class="text-[10px] text-slate-500 mt-1 italic leading-tight">
                        {$_('detection.video_analysis.verified_desc')}
                    </p>
                </div>
            {:else if detection.video_classification_status === 'processing' || detection.video_classification_status === 'pending'}
                 <div class="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/70 dark:border-slate-700/50 flex items-center gap-3 animate-pulse">
                    <div class="w-4 h-4 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin"></div>
                    <span class="text-xs font-bold text-slate-500 uppercase tracking-widest">{$_('detection.video_analysis.in_progress')}</span>
                 </div>
            {:else if detection.video_classification_status === 'failed'}
                <div class="p-4 rounded-2xl bg-rose-50/80 dark:bg-rose-500/10 border border-rose-200/70 dark:border-rose-500/20 animate-in fade-in slide-in-from-top-2">
                    <p class="text-[10px] font-black text-rose-600 dark:text-rose-400 uppercase tracking-[0.2em] mb-1">
                        {$_('detection.video_analysis.failed_title')}
                    </p>
                    <p class="text-xs text-slate-600 dark:text-slate-300">
                        {getVideoFailureMessage(detection.video_classification_error)}
                    </p>
                </div>
            {/if}

            <!-- Metadata -->
            <div class="grid grid-cols-2 gap-4">
                <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50">
                    <svg class="w-4 h-4 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                    </svg>
                    <span class="text-sm font-bold text-slate-700 dark:text-slate-300 truncate">{detection.camera_name}</span>
                </div>
                {#if detection.temperature !== undefined && detection.temperature !== null}
                    <div class="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50">
                        <svg class="w-4 h-4 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
                        </svg>
                        <span class="text-sm font-bold text-slate-700 dark:text-slate-300">
                            {formatTemperature(detection.temperature, settingsStore.settings?.location_temperature_unit)}
                        </span>
                    </div>
                {/if}
            </div>

            <!-- AI Analysis -->
            {#if llmEnabled && aiAnalysis}
                <div class="space-y-3">
                    <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 animate-in fade-in slide-in-from-top-2">
                        <p class="text-[10px] font-black text-teal-600 dark:text-teal-400 uppercase tracking-[0.2em] mb-2">
                            {$_('detection.ai.insight')}
                        </p>
                        <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">{aiAnalysis}</p>
                    </div>
                    <button
                        onclick={() => handleAIAnalysis(true)}
                        disabled={analyzingAI}
                        class="w-full py-2 px-4 bg-teal-500/10 hover:bg-teal-500/20 text-teal-600 dark:text-teal-400 font-semibold text-sm rounded-xl transition-all flex items-center justify-center gap-2 border border-teal-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                        title={$_('detection.ai.regenerate')}
                    >
                        <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                        {analyzingAI ? $_('detection.ai.regenerating') : $_('detection.ai.regenerate')}
                    </button>
                </div>
            {:else if llmEnabled && !analyzingAI}
                <button
                    onclick={() => handleAIAnalysis()}
                    class="w-full py-3 px-4 bg-teal-500/10 hover:bg-teal-500/20 text-teal-600 dark:text-teal-400 font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-teal-500/20"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    {$_('detection.ai.ask')}
                </button>
            {:else if analyzingAI}
                <div class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-500 font-bold rounded-xl flex items-center justify-center gap-3 animate-pulse">
                    <div class="w-4 h-4 border-2 border-teal-500 border-t-transparent rounded-full animate-spin"></div>
                    {$_('detection.ai.analyzing')}
                </div>
            {/if}

            <!-- Actions -->
            <div class="flex gap-2">
                <button
                    onclick={handleReclassifyClick}
                    class="flex-1 py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors"
                >
                    {$_('actions.reclassify')}
                </button>

                <div class="relative flex-1">
                    <button
                        onclick={() => showTagDropdown = !showTagDropdown}
                        disabled={updatingTag}
                        class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-700 text-slate-700 dark:text-slate-200 font-bold rounded-xl hover:bg-slate-200 transition-colors disabled:opacity-50"
                    >
                        {updatingTag ? $_('common.saving') : $_('actions.manual_tag')}
                    </button>
                </div>
            </div>

            <!-- Bottom Actions -->
            <div class="flex gap-2 pt-2">
                <button
                    onclick={handleDelete}
                    class="p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 hover:bg-red-100 transition-colors"
                    title={$_('actions.delete_detection')}
                >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" />
                    </svg>
                </button>
                <button
                    onclick={handleHide}
                    class="p-3 rounded-xl bg-slate-100 dark:bg-slate-700 text-slate-600 hover:bg-slate-200 transition-colors"
                    title={$_('actions.hide_detection')}
                >
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.875 18.825A10.05 10.05 0 0112 19c-4.478 0-8.268-2.943-9.543-7a9.97 9.97 0 011.563-3.029m5.858.908a3 3 0 114.243 4.243M9.878 9.878l4.242 4.242M9.88 9.88l-3.29-3.29m7.532 7.532l3.29 3.29M3 3l3.59 3.59m0 0A9.953 9.953 0 0112 5c4.478 0 8.268 2.943 9.543 7a10.025 10.025 0 01-4.132 5.411m0 0L21 21" />
                    </svg>
                </button>
                <button
                    onclick={handleSpeciesInfo}
                    class="flex-1 bg-teal-500 hover:bg-teal-600 text-white font-black uppercase tracking-widest text-xs rounded-xl transition-all shadow-lg shadow-teal-500/20"
                >
                    {$_('actions.species_info')}
                </button>
            </div>
        </div>

        {#if showTagDropdown}
            <div class="absolute inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
                <div class="w-full max-w-md mx-6 bg-white dark:bg-slate-800 rounded-2xl shadow-2xl border border-slate-200 dark:border-slate-700 overflow-hidden animate-in fade-in zoom-in-95">
                    <div class="px-5 py-4 border-b border-slate-100 dark:border-slate-700 flex items-center justify-between">
                        <h4 class="text-sm font-black text-slate-800 dark:text-slate-100 uppercase tracking-widest">
                            {$_('actions.manual_tag')}
                        </h4>
                        <button
                            onclick={() => showTagDropdown = false}
                            class="text-xs font-bold text-slate-500 hover:text-slate-700 dark:text-slate-400 dark:hover:text-slate-200"
                        >
                            {$_('common.cancel')}
                        </button>
                    </div>
                    <div class="p-4 border-b border-slate-100 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50">
                        <input
                            type="text"
                            bind:value={tagSearchQuery}
                            placeholder={$_('detection.tagging.search_placeholder')}
                            class="w-full px-4 py-2 text-sm rounded-xl border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-700 text-slate-900 dark:text-white focus:ring-2 focus:ring-teal-500 focus:border-transparent outline-none"
                        />
                    </div>
                    <div class="max-h-72 overflow-y-auto p-1">
                        {#each searchResults as result}
                            {@const names = getResultNames(result)}
                            <button
                                onclick={() => handleManualTag(result.id)}
                                class="w-full px-4 py-2.5 text-left text-sm font-medium rounded-lg transition-all hover:bg-teal-50 dark:hover:bg-teal-900/20 hover:text-teal-600 dark:hover:text-teal-400 {result.id === detection.display_name ? 'bg-teal-500/10 text-teal-600 font-bold' : 'text-slate-600 dark:text-slate-300'}"
                            >
                                <span class="block text-sm leading-tight">{names.primary}</span>
                                {#if names.secondary}
                                    <span class="block text-[11px] text-slate-400 dark:text-slate-400 italic">{names.secondary}</span>
                                {/if}
                            </button>
                        {/each}
                        {#if searchResults.length === 0}
                            <p class="px-4 py-6 text-sm text-slate-400 italic text-center">
                                {isSearching ? $_('common.loading') : $_('detection.tagging.no_results')}
                            </p>
                        {/if}
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
