<script lang="ts">
    import { getThumbnailUrl, analyzeDetection, updateDetectionSpecies, hideDetection, deleteDetection, searchSpecies, fetchAudioContext, createInaturalistDraft, submitInaturalistObservation, type SearchResult, type AudioContextDetection, type InaturalistDraft } from '../api';
    import type { Detection } from '../api';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import { detectionsStore, type ReclassificationProgress } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
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
        onReclassify?: (detection: Detection) => void;
        onPlayVideo?: () => void;
        onViewSpecies: (speciesName: string) => void;
        readOnly?: boolean;
    }

    let {
        detection,
        classifierLabels,
        llmEnabled,
        showVideoButton = false,
        onClose,
        onReclassify,
        onPlayVideo,
        onViewSpecies,
        readOnly = false
    }: Props = $props();

    // State
    let modalElement = $state<HTMLElement | null>(null);
    let analyzingAI = $state(false);
    let audioContextOpen = $state(false);
    let audioContextLoading = $state(false);
    let audioContextLoaded = $state(false);
    let audioContext = $state<AudioContextDetection[]>([]);
    let audioContextError = $state<string | null>(null);
    let weatherDetailsOpen = $state(false);
    let inatPanelOpen = $state(false);
    let inatLoading = $state(false);
    let inatSubmitting = $state(false);
    let inatError = $state<string | null>(null);
    let inatDraft = $state<InaturalistDraft | null>(null);
    let inatNotes = $state('');
    let inatLat = $state<number | null>(null);
    let inatLon = $state<number | null>(null);
    let inatPlace = $state('');

    $effect(() => {
        if (modalElement) {
            return trapFocus(modalElement);
        }
    });

    let aiAnalysis = $state<string | null>(null);
    let lastEventId = $state<string | null>(null);
    let showTagDropdown = $state(false);
    let updatingTag = $state(false);
    let tagSearchQuery = $state('');
    let searchResults = $state<SearchResult[]>([]);
    let isSearching = $state(false);

    type AiBlock =
        | { type: 'heading'; text: string }
        | { type: 'paragraph'; text: string };

    function parseAiAnalysis(text: string): AiBlock[] {
        const lines = text
            .split(/\r?\n/)
            .map(line => line.trim())
            .filter(Boolean);

        const blocks: AiBlock[] = [];

        for (const line of lines) {
            const headingMatch = line.match(/^#{1,6}\s+(.*)$/);
            if (headingMatch) {
                blocks.push({ type: 'heading', text: headingMatch[1] });
                continue;
            }

            const listMatch = line.match(/^[-*•]\s+(.*)$/);
            if (listMatch) {
                const last = blocks[blocks.length - 1];
                if (last?.type === 'paragraph') {
                    last.text = `${last.text} ${listMatch[1]}`.trim();
                } else {
                    blocks.push({ type: 'paragraph', text: listMatch[1] });
                }
                continue;
            }
            blocks.push({ type: 'paragraph', text: line });
        }

        return blocks;
    }

    let aiBlocks = $derived(() => (aiAnalysis ? parseAiAnalysis(aiAnalysis) : []));

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
    const hasAudioContext = $derived(!!detection.audio_species || detection.audio_confirmed);
    const hasWeather = $derived(
        detection.temperature !== undefined && detection.temperature !== null ||
        !!detection.weather_condition ||
        detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null ||
        detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null ||
        detection.weather_precipitation !== undefined && detection.weather_precipitation !== null ||
        detection.weather_rain !== undefined && detection.weather_rain !== null ||
        detection.weather_snowfall !== undefined && detection.weather_snowfall !== null
    );
    const inatEnabled = $derived(settingsStore.settings?.inaturalist_enabled ?? false);
    const inatConnectedUser = $derived(settingsStore.settings?.inaturalist_connected_user ?? null);
    const canShowInat = $derived(!readOnly && authStore.canModify && inatEnabled && !!inatConnectedUser);

    $effect(() => {
        if (!detection?.frigate_event) return;
        if (detection.frigate_event !== lastEventId) {
            lastEventId = detection.frigate_event;
            aiAnalysis = detection.ai_analysis || null;
            inatPanelOpen = false;
            inatDraft = null;
            inatNotes = '';
            inatLat = null;
            inatLon = null;
            inatPlace = '';
        }
    });

    async function openInatPanel() {
        inatPanelOpen = !inatPanelOpen;
        if (!inatPanelOpen || !detection?.frigate_event) {
            return;
        }
        if (inatDraft && inatDraft.event_id === detection.frigate_event) {
            return;
        }
        inatLoading = true;
        inatError = null;
        try {
            inatDraft = await createInaturalistDraft(detection.frigate_event);
            inatNotes = '';
            inatLat = inatDraft.latitude ?? null;
            inatLon = inatDraft.longitude ?? null;
            inatPlace = inatDraft.place_guess ?? '';
        } catch (e: any) {
            inatError = e?.message || 'Failed to load iNaturalist draft';
        } finally {
            inatLoading = false;
        }
    }

    async function submitInat() {
        if (!inatDraft) return;
        inatSubmitting = true;
        inatError = null;
        try {
            await submitInaturalistObservation({
                event_id: inatDraft.event_id,
                notes: inatNotes || undefined,
                latitude: inatLat ?? undefined,
                longitude: inatLon ?? undefined,
                place_guess: inatPlace || undefined
            });
            inatPanelOpen = false;
            inatNotes = '';
            inatLat = inatDraft.latitude ?? null;
            inatLon = inatDraft.longitude ?? null;
            inatPlace = inatDraft.place_guess ?? '';
        } catch (e: any) {
            inatError = e?.message || 'Failed to submit to iNaturalist';
        } finally {
            inatSubmitting = false;
        }
    }

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

    function formatWindDirection(deg?: number | null): string {
        if (deg === null || deg === undefined || Number.isNaN(deg)) return '';
        const directions = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW'];
        const index = Math.round(((deg % 360) / 45)) % 8;
        return directions[index];
    }

    function formatPrecip(value?: number | null): string {
        if (value === null || value === undefined || Number.isNaN(value)) return '';
        if (value < 0.1) return `${value.toFixed(2)}mm`;
        if (value < 1) return `${value.toFixed(1)}mm`;
        return `${value.toFixed(0)}mm`;
    }

    function formatAudioOffset(offsetSeconds: number): string {
        const abs = Math.abs(offsetSeconds);
        const mins = Math.floor(abs / 60);
        const secs = abs % 60;
        const label = mins > 0 ? `${mins}m` : `${secs}s`;
        if (offsetSeconds === 0) return '0s';
        return `${offsetSeconds > 0 ? '+' : '-'}${label}`;
    }

    async function toggleAudioContext(event: MouseEvent) {
        event.stopPropagation();
        audioContextOpen = !audioContextOpen;
        if (audioContextOpen && !audioContextLoaded && !audioContextLoading) {
            audioContextLoading = true;
            audioContextError = null;
            try {
                audioContext = await fetchAudioContext(
                    detection.detection_time,
                    detection.camera_name,
                    300,
                    6
                );
                audioContextLoaded = true;
            } catch (e) {
                audioContextError = $_('common.error');
            } finally {
                audioContextLoading = false;
            }
        }
    }

    async function handleAIAnalysis(force: boolean = false) {
        if (readOnly) return;
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
        if (readOnly) return;
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
        if (readOnly) return;
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
        if (readOnly) return;
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
        if (readOnly || !onReclassify) return;
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
                            {formatTemperature(detection.temperature, settingsStore.settings?.location_temperature_unit as any)}
                        </span>
                    </div>
                {/if}
            </div>

            {#if hasAudioContext}
                <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 dark:border-teal-500/20 space-y-3">
                    <div class="flex items-center gap-3">
                        <div class="w-10 h-10 rounded-xl bg-teal-500/20 flex items-center justify-center">
                            <svg class="w-5 h-5 text-teal-600 dark:text-teal-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                            </svg>
                        </div>
                        <div class="min-w-0">
                            <p class="text-[10px] font-black uppercase tracking-widest text-teal-600/70 dark:text-teal-400/70">
                                {$_('detection.audio_match')}
                            </p>
                            <p class="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">
                                {detection.audio_species || $_('detection.birdnet_confirmed')}
                                {#if detection.audio_score}
                                    <span class="ml-1 opacity-60">({(detection.audio_score * 100).toFixed(0)}%)</span>
                                {/if}
                            </p>
                        </div>
                    </div>
                    <button
                        type="button"
                        onclick={toggleAudioContext}
                        class="text-[10px] font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-2"
                        aria-label={$_('detection.audio_context')}
                    >
                        <svg class="w-3 h-3 transition-transform {audioContextOpen ? 'rotate-180' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                        <span>{$_('detection.audio_context')}</span>
                    </button>
                    {#if audioContextOpen}
                        <div class="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 p-3 space-y-2">
                            {#if audioContextLoading}
                                <p class="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{$_('detection.audio_context_loading')}</p>
                            {:else if audioContextError}
                                <p class="text-[10px] font-semibold uppercase tracking-widest text-rose-500">{audioContextError}</p>
                            {:else if audioContext.length === 0}
                                <p class="text-[10px] font-semibold uppercase tracking-widest text-slate-400">{$_('detection.audio_context_empty')}</p>
                            {:else}
                                {#each audioContext as audio}
                                    <div class="flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
                                        <div class="min-w-0">
                                            <p class="font-semibold truncate">{audio.species}</p>
                                            <p class="text-[10px] uppercase tracking-widest text-slate-400">
                                                {(audio.confidence * 100).toFixed(0)}%
                                                {#if audio.sensor_id}
                                                    <span class="ml-1 opacity-70">{audio.sensor_id}</span>
                                                {/if}
                                            </p>
                                        </div>
                                        <div class="text-[10px] font-black text-slate-500 dark:text-slate-400">
                                            {formatAudioOffset(audio.offset_seconds)}
                                        </div>
                                    </div>
                                {/each}
                            {/if}
                        </div>
                    {/if}
                </div>
            {/if}

            {#if hasWeather}
                <div class="p-4 rounded-2xl bg-sky-50/80 dark:bg-slate-900/40 border border-sky-100/80 dark:border-slate-700/60 space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-3 min-w-0">
                            <div class="w-10 h-10 rounded-xl bg-sky-500/20 flex items-center justify-center flex-shrink-0">
                                <svg class="w-5 h-5 text-sky-600 dark:text-sky-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                </svg>
                            </div>
                            <div class="min-w-0">
                                <p class="text-[10px] font-black uppercase tracking-widest text-sky-600/70 dark:text-sky-300/70 mb-0.5">
                                    {$_('detection.weather_title')}
                                </p>
                                <p class="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">
                                    {detection.weather_condition || $_('detection.weather_unknown')}
                                </p>
                            </div>
                        </div>
                        {#if detection.temperature !== undefined && detection.temperature !== null}
                            <div class="text-sm font-black text-slate-800 dark:text-slate-100">
                                {formatTemperature(detection.temperature, settingsStore.settings?.location_temperature_unit as any)}
                            </div>
                        {/if}
                    </div>
                    <button
                        type="button"
                        onclick={(event) => { event.stopPropagation(); weatherDetailsOpen = !weatherDetailsOpen; }}
                        class="text-[10px] font-semibold text-slate-500 dark:text-slate-400 flex items-center gap-2"
                        aria-label={$_('detection.weather_details')}
                    >
                        <svg class="w-3 h-3 transition-transform {weatherDetailsOpen ? 'rotate-180' : ''}" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7" />
                        </svg>
                        <span>{$_('detection.weather_details')}</span>
                    </button>
                    {#if weatherDetailsOpen}
                        <div class="grid grid-cols-2 gap-2">
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 8h11a3 3 0 100-6M2 12h13a3 3 0 110 6H9" />
                                    </svg>
                                    {$_('detection.weather_wind')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {#if detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null}
                                        {Math.round(detection.weather_wind_speed)} km/h {formatWindDirection(detection.weather_wind_direction)}
                                    {:else}
                                        —
                                    {/if}
                                </p>
                            </div>
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                    </svg>
                                    {$_('detection.weather_cloud')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {#if detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null}
                                        {Math.round(detection.weather_cloud_cover)}%
                                    {:else}
                                        —
                                    {/if}
                                </p>
                            </div>
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" />
                                    </svg>
                                    {$_('detection.weather_title')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {detection.weather_condition || $_('detection.weather_unknown')}
                                </p>
                            </div>
                            <div class="rounded-xl bg-white/80 dark:bg-slate-900/50 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                <div class="flex items-center gap-2 text-[9px] font-black uppercase tracking-widest text-slate-400">
                                    <svg class="w-3 h-3 text-indigo-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v18m9-9H3m15.364-6.364l-12.728 12.728m0-12.728l12.728 12.728" />
                                    </svg>
                                    {$_('detection.weather_rain')} / {$_('detection.weather_snow')}
                                </div>
                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200">
                                    {#if detection.weather_rain !== undefined && detection.weather_rain !== null || detection.weather_snowfall !== undefined && detection.weather_snowfall !== null}
                                        {formatPrecip(detection.weather_rain)} / {formatPrecip(detection.weather_snowfall)}
                                    {:else}
                                        —
                                    {/if}
                                </p>
                            </div>
                        </div>
                    {/if}
                </div>
            {/if}

            {#if canShowInat}
                <div class="p-4 rounded-2xl bg-emerald-50/70 dark:bg-slate-900/40 border border-emerald-100/80 dark:border-slate-700/60 space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-3">
                            <div class="w-9 h-9 rounded-xl bg-emerald-500/20 flex items-center justify-center text-emerald-600 dark:text-emerald-300">
                                <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 3v4m0 0a4 4 0 110 8m0-8a4 4 0 10-4 4m4-4v4m0 0a4 4 0 010 8m0-8a4 4 0 10-4 4" />
                                </svg>
                            </div>
                            <div>
                                <p class="text-[10px] font-black uppercase tracking-widest text-emerald-600/80 dark:text-emerald-300/80">{$_('detection.inat.title')}</p>
                                <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{$_('detection.inat.connected', { values: { user: inatConnectedUser } })}</p>
                            </div>
                        </div>
                        <button
                            type="button"
                            onclick={openInatPanel}
                            class="px-3 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white transition-all"
                            aria-label={$_('detection.inat.open_label')}
                        >
                            {inatPanelOpen ? $_('detection.inat.close') : $_('detection.inat.open')}
                        </button>
                    </div>

                    {#if inatPanelOpen}
                        <div class="space-y-3">
                            {#if inatLoading}
                                <div class="text-xs font-semibold text-emerald-600/80">{$_('detection.inat.loading')}</div>
                            {:else}
                                {#if inatError}
                                    <div class="text-xs font-semibold text-rose-600">{inatError}</div>
                                {/if}
                                {#if inatDraft}
                                    <div class="grid grid-cols-2 gap-3 text-[11px] text-slate-600 dark:text-slate-300">
                                        <div class="rounded-xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                            <p class="text-[9px] font-black uppercase tracking-widest text-slate-400">{$_('detection.inat.species')}</p>
                                            <p class="font-semibold text-slate-700 dark:text-slate-200">{inatDraft.species_guess}</p>
                                        </div>
                                        <div class="rounded-xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                            <p class="text-[9px] font-black uppercase tracking-widest text-slate-400">{$_('detection.inat.observed')}</p>
                                            <p class="font-semibold text-slate-700 dark:text-slate-200">{new Date(inatDraft.observed_on_string).toLocaleString()}</p>
                                        </div>
                                    </div>
                                    <div class="grid grid-cols-2 gap-3">
                                        <div>
                                            <label class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.latitude')}</label>
                                            <input
                                                type="number"
                                                step="0.0001"
                                                bind:value={inatLat}
                                                class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                            />
                                        </div>
                                        <div>
                                            <label class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.longitude')}</label>
                                            <input
                                                type="number"
                                                step="0.0001"
                                                bind:value={inatLon}
                                                class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                            />
                                        </div>
                                    </div>
                                    <div>
                                        <label class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.place')}</label>
                                        <input
                                            type="text"
                                            bind:value={inatPlace}
                                            class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                        />
                                    </div>
                                    <div>
                                        <label class="block text-[9px] font-black uppercase tracking-widest text-slate-400 mb-1">{$_('detection.inat.notes')}</label>
                                        <textarea
                                            rows="3"
                                            bind:value={inatNotes}
                                            class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/50 text-xs font-bold"
                                        ></textarea>
                                    </div>
                                    <button
                                        type="button"
                                        onclick={submitInat}
                                        disabled={inatSubmitting}
                                        class="w-full py-2 px-4 rounded-xl bg-emerald-500 hover:bg-emerald-600 text-white text-xs font-black uppercase tracking-widest disabled:opacity-50"
                                    >
                                        {inatSubmitting ? $_('detection.inat.submitting') : $_('detection.inat.submit')}
                                    </button>
                                {/if}
                            {/if}
                        </div>
                    {/if}
                </div>
            {/if}

            <!-- AI Analysis -->
            {#if aiAnalysis}
                <div class="space-y-3">
                    <div class="p-4 rounded-2xl bg-teal-500/5 border border-teal-500/10 animate-in fade-in slide-in-from-top-2">
                        <p class="text-[10px] font-black text-teal-600 dark:text-teal-400 uppercase tracking-[0.2em] mb-2">
                            {$_('detection.ai.insight')}
                        </p>
                        <div class="space-y-2">
                            {#each aiBlocks() as block}
                                {#if block.type === 'heading'}
                                    <p class="text-[11px] font-black uppercase tracking-[0.2em] text-teal-700 dark:text-teal-300">{block.text}</p>
                                {:else}
                                    <p class="text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">{block.text}</p>
                                {/if}
                            {/each}
                        </div>
                    </div>
                    {#if authStore.canModify && llmEnabled}
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
                    {/if}
                </div>
            {:else if llmEnabled && !analyzingAI && authStore.canModify}
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
            {#if authStore.canModify}
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
            {/if}

            <!-- Bottom Actions -->
            <div class="flex gap-2 pt-2">
                {#if authStore.canModify}
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
                {/if}
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
