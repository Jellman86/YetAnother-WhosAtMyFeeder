<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fly } from 'svelte/transition';
    import { flip } from 'svelte/animate';
    import { cubicOut } from 'svelte/easing';
    import { fetchRecentAudio, fetchAudioSummary, type AudioDetection, type AudioSummaryResponse } from '../api';
    import { withAuthParams } from '../api/core';
    import { fetchSettings } from '../api/settings';
    import { appApiPath } from '../app/url-base';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    let { onNavigate }: { onNavigate?: (path: string) => void } = $props();

    const RECENT_AUDIO_LIMIT = 10;

    function detectionKey(d: AudioDetection, index: number): string {
        // birdnet_id is stable when present; otherwise compose a key that is
        // stable across polls so flip animations track moves rather than swap.
        // The trailing index protects against the rare collision where two
        // legacy detections (no birdnet_id) share the same timestamp,
        // species, and sensor — Svelte's keyed each block would otherwise
        // throw `each_key_duplicate`.
        if (d.birdnet_id != null) return `bn:${d.birdnet_id}`;
        return `${d.timestamp}|${d.species}|${d.sensor_id ?? ''}|${index}`;
    }

    let audioDetections = $state<AudioDetection[]>([]);
    let pollInterval: any;
    let summaryInterval: any;
    let loading = $state(true);
    let birdnetExternalUrl = $state('');
    let summary = $state<AudioSummaryResponse | null>(null);

    // Compact 24-hour sparkline for the header strip. Built as a normalized
    // SVG polyline so the widget stays light (no ApexCharts on the dashboard).
    let sparkline = $derived.by(() => {
        const counts = new Array(24).fill(0);
        for (const item of summary?.hourly_counts ?? []) {
            if (item.hour >= 0 && item.hour < 24) counts[item.hour] = item.count;
        }
        const max = Math.max(...counts, 1);
        const w = 100;
        const h = 24;
        const step = counts.length > 1 ? w / (counts.length - 1) : w;
        const points = counts.map((c, i) => `${(i * step).toFixed(1)},${(h - (c / max) * h).toFixed(1)}`);
        return { points: points.join(' '), area: `0,${h} ${points.join(' ')} ${w},${h}`, hasData: counts.some((c) => c > 0) };
    });

    async function loadAudio() {
        try {
            audioDetections = await fetchRecentAudio(RECENT_AUDIO_LIMIT);
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

    async function loadSummary() {
        try {
            summary = await fetchAudioSummary({ days: 1 });
        } catch (e) {
            if (isTransientRequestError(e)) {
                logger.warn('Audio summary fetch failed (transient)', { message: getErrorMessage(e) });
            } else {
                logger.error('Failed to fetch audio summary', e);
            }
        }
    }

    async function loadBirdnetUrl() {
        if (!authStore.showSettings) {
            birdnetExternalUrl = '';
            return;
        }
        try {
            const settings = await fetchSettings();
            birdnetExternalUrl = settings.birdnet_external_url || settings.birdnet_url || '';
        } catch {
            birdnetExternalUrl = '';
        }
    }

    function spectrogramUrl(birdnet_id: number | null | undefined): string | null {
        if (!birdnet_id) return null;
        // The spectrogram is loaded as a CSS background-image, which cannot send
        // auth headers — append the JWT as a query param so it works when
        // authentication is enabled (mirrors Frigate media URLs).
        return withAuthParams(`${appApiPath(`/audio/spectrogram/${birdnet_id}`)}?width=600`);
    }

    function birdnetDetectionUrl(birdnet_id: number | null | undefined): string | null {
        if (!birdnetExternalUrl || !birdnet_id) return null;
        return `${birdnetExternalUrl.replace(/\/$/, '')}/ui/detections/${birdnet_id}`;
    }

    onMount(() => {
        loadAudio();
        loadSummary();
        loadBirdnetUrl();
        pollInterval = setInterval(loadAudio, 5000);
        // Summary rollups change slowly — refresh on a longer cadence to limit load.
        summaryInterval = setInterval(loadSummary, 60000);
    });

    onDestroy(() => {
        if (pollInterval) clearInterval(pollInterval);
        if (summaryInterval) clearInterval(summaryInterval);
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
        <div class="flex items-center gap-2">
            <button
                type="button"
                class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-teal-50 dark:bg-teal-950/40 text-teal-700 dark:text-teal-300 hover:bg-teal-100 dark:hover:bg-teal-900/50 transition-colors text-[9px] font-black uppercase tracking-wider"
                title={$_('dashboard.audio_feed.open_history', { default: 'Open audio history' })}
                onclick={() => onNavigate?.('/audio')}
            >
                <span>History</span>
                <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M9 5l7 7-7 7" />
                </svg>
            </button>
            {#if !loading && audioDetections.length > 0}
                <div class="flex items-center gap-1.5 px-2 py-1 rounded-full bg-green-100 dark:bg-green-500/20 text-green-800 dark:text-green-200">
                    <div class="w-1.5 h-1.5 rounded-full bg-green-500"></div>
                    <span class="text-[9px] font-black uppercase tracking-wider">{$_('dashboard.audio_feed.active')}</span>
                </div>
            {/if}
            {#if birdnetExternalUrl}
                <a
                    href={birdnetExternalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex items-center gap-1 px-2 py-1 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 hover:bg-teal-50 dark:hover:bg-teal-950/40 hover:text-teal-700 dark:hover:text-teal-300 transition-colors text-[9px] font-black uppercase tracking-wider"
                    title={$_('dashboard.audio_feed.open_birdnet', { default: 'Open BirdNET-Go' })}
                >
                    <span>BirdNET-Go</span>
                    <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M14 5h5v5M19 5L10 14M5 7v12h12" />
                    </svg>
                </a>
            {/if}
        </div>
    </div>

    {#if summary && summary.total > 0}
        <div class="mb-4 flex items-center gap-4 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50 px-3.5 py-2.5">
            <div class="flex items-baseline gap-1.5">
                <span class="text-lg font-black text-teal-700 dark:text-teal-300 leading-none">{summary.total.toLocaleString()}</span>
                <span class="text-[9px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.heard_today', { default: 'heard' })}</span>
            </div>
            <div class="w-px h-6 bg-slate-200 dark:bg-slate-700"></div>
            <div class="flex items-baseline gap-1.5">
                <span class="text-lg font-black text-slate-800 dark:text-slate-100 leading-none">{summary.species_count}</span>
                <span class="text-[9px] font-black uppercase tracking-wider text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.species', { default: 'species' })}</span>
            </div>
            {#if sparkline.hasData}
                <svg viewBox="0 0 100 24" preserveAspectRatio="none" class="ml-auto h-6 w-24 flex-shrink-0 overflow-visible" aria-hidden="true">
                    <polyline points={sparkline.area} fill="currentColor" class="text-teal-500/15" stroke="none" />
                    <polyline points={sparkline.points} fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" class="text-teal-500 dark:text-teal-400" vector-effect="non-scaling-stroke" />
                </svg>
            {/if}
        </div>
    {/if}

    <div class="space-y-3 flex-1">
        {#if loading}
            {#each Array.from({ length: 6 }) as _}
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
            {#each audioDetections as detection, i (detectionKey(detection, i))}
                {@const spec = spectrogramUrl(detection.birdnet_id)}
                {@const link = birdnetDetectionUrl(detection.birdnet_id)}
                <div
                    animate:flip={{ duration: 350, easing: cubicOut }}
                    in:fly={{ y: -24, duration: 320, easing: cubicOut }}
                    out:fly={{ y: 28, duration: 260, easing: cubicOut }}
                >
                {#snippet body()}
                    {#if spec}
                        <img
                            src={spec}
                            alt=""
                            aria-hidden="true"
                            loading="lazy"
                            class="absolute inset-0 w-full h-full object-cover opacity-55 dark:opacity-45 transition-opacity pointer-events-none select-none"
                        />
                        <div class="absolute inset-0 bg-gradient-to-r from-white/90 via-white/55 to-white/15 dark:from-slate-900/90 dark:via-slate-900/55 dark:to-slate-900/15"></div>
                    {/if}
                    <div class="relative">
                        <div class="flex items-center justify-between gap-3 mb-1">
                            <span class="text-[10px] font-black text-teal-700 dark:text-teal-300 uppercase tracking-tighter">{formatTimeWithSeconds(detection.timestamp)}</span>
                            <span class="text-[10px] font-black text-slate-600 dark:text-slate-400 uppercase tracking-widest">{detection.sensor_id || $_('dashboard.audio_feed.unknown_sensor')}</span>
                        </div>
                        <div class="flex items-center justify-between gap-4">
                            <p class="text-sm font-black text-slate-800 dark:text-slate-100 truncate">{detection.species}</p>
                            <div class="flex items-center gap-1.5 flex-shrink-0">
                                <div class="w-1.5 h-1.5 rounded-full {detection.confidence > 0.7 ? 'bg-green-500' : 'bg-amber-500'}"></div>
                                <span class="text-xs font-black {detection.confidence > 0.7 ? 'text-green-700 dark:text-green-300' : 'text-amber-700 dark:text-amber-300'}">{(detection.confidence * 100).toFixed(0)}%</span>
                            </div>
                        </div>
                    </div>
                {/snippet}
                {#if link}
                    <a
                        href={link}
                        target="_blank"
                        rel="noopener noreferrer"
                        class="relative block overflow-hidden p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50 hover:border-teal-500/30 hover:ring-1 hover:ring-teal-500/20 transition-all"
                        title={$_('dashboard.audio_feed.open_in_birdnet', { default: 'Open detection in BirdNET-Go' })}
                    >
                        {@render body()}
                    </a>
                {:else}
                    <div class="relative overflow-hidden p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-900/40 border border-slate-100 dark:border-slate-700/50 hover:border-teal-500/30 transition-all">
                        {@render body()}
                    </div>
                {/if}
                </div>
            {/each}
        {/if}
    </div>
</section>
