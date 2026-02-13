<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchRecentAudio, type AudioDetection } from '../api';
    import { formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    let audioDetections = $state<AudioDetection[]>([]);
    let pollInterval: any;
    let loading = $state(true);

    async function loadAudio() {
        try {
            audioDetections = await fetchRecentAudio(5);
        } catch (e) {
            if (isTransientRequestError(e)) {
                logger.warn('Recent audio fetch failed (transient)', {
                    message: getErrorMessage(e)
                });
            } else {
                logger.error('Failed to fetch recent audio', e);
            }
        } finally {
            loading = false;
        }
    }

    onMount(() => {
        loadAudio();
        pollInterval = setInterval(loadAudio, 5000);
    });

    onDestroy(() => {
        if (pollInterval) clearInterval(pollInterval);
    });

    function formatTimeWithSeconds(dateString: string): string {
        return formatTime(dateString, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
</script>

<section class="card-base rounded-3xl p-6 backdrop-blur-md h-full flex flex-col">
    <div class="flex items-center justify-between mb-6">
        <div class="flex items-center gap-3">
            <div class="w-10 h-10 rounded-2xl bg-teal-500/10 flex items-center justify-center text-teal-600 dark:text-teal-400">
                <svg class="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
                </svg>
            </div>
            <div>
                <h3 class="text-lg font-black text-slate-900 dark:text-white tracking-tight">{$_('dashboard.audio_feed.title')}</h3>
                <p class="text-[10px] font-bold text-slate-500 uppercase tracking-widest">{$_('dashboard.audio_feed.subtitle')}</p>
            </div>
        </div>
        {#if !loading && audioDetections.length > 0}
            <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-emerald-100 dark:bg-emerald-500/20 text-emerald-800 dark:text-emerald-200">
                <div class="w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                <span class="text-[9px] font-black uppercase tracking-wider">{$_('dashboard.audio_feed.active')}</span>
            </div>
        {/if}
    </div>

    <div class="space-y-3 flex-1">
        {#if loading}
            {#each [1, 2, 3] as _}
                <div class="h-16 bg-slate-100 dark:bg-slate-800/50 rounded-2xl animate-pulse border border-slate-200/50 dark:border-slate-700/50"></div>
            {/each}
        {:else if audioDetections.length === 0}
            <div class="flex flex-col items-center justify-center py-12 text-center">
                <div class="w-12 h-12 rounded-full bg-slate-100 dark:bg-slate-800 flex items-center justify-center mb-3">
                    <svg class="w-6 h-6 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                    </svg>
                </div>
                <p class="text-xs font-bold text-slate-400 italic">{$_('dashboard.audio_feed.empty_title')}</p>
                <p class="text-[9px] text-slate-500 mt-1 uppercase tracking-widest">{$_('dashboard.audio_feed.empty_subtitle')}</p>
            </div>
        {:else}
            {#each audioDetections as detection}
                <div class="group p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50 hover:border-teal-500/30 transition-all">
                    <div class="flex items-center justify-between gap-3 mb-1">
                        <span class="text-[10px] font-black text-teal-700 dark:text-teal-300 uppercase tracking-tighter">{formatTimeWithSeconds(detection.timestamp)}</span>
                        <span class="text-[10px] font-black text-slate-600 dark:text-slate-400 uppercase tracking-widest">{detection.sensor_id || $_('dashboard.audio_feed.unknown_sensor')}</span>
                    </div>
                    <div class="flex items-center justify-between gap-4">
                        <p class="text-sm font-black text-slate-800 dark:text-slate-100 truncate">{detection.species}</p>
                        <div class="flex items-center gap-1.5 flex-shrink-0">
                            <div class="w-1.5 h-1.5 rounded-full {detection.confidence > 0.7 ? 'bg-emerald-500' : 'bg-amber-500'}"></div>
                            <span class="text-xs font-black {detection.confidence > 0.7 ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}">{(detection.confidence * 100).toFixed(0)}%</span>
                        </div>
                    </div>
                </div>
            {/each}
        {/if}
    </div>
</section>
