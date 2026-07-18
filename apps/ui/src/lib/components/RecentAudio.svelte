<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchRecentAudio, fetchAudioSummary, type AudioDetection, type AudioSummaryResponse } from '../api';
    import { withAuthParams } from '../api/core';
    import { fetchSettings } from '../api/settings';
    import { appApiPath } from '../app/url-base';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    let { onNavigate }: { onNavigate?: (path: string) => void } = $props();

    const RECENT_AUDIO_LIMIT = 4;

    function detectionKey(d: AudioDetection, index: number): string {
        // birdnet_id is stable when present; otherwise compose a key that is
        // stable across polls so keyed rows track moves rather than swap.
        // The trailing index protects against the rare collision where two
        // legacy detections (no birdnet_id) share the same timestamp,
        // species, and sensor — Svelte's keyed each block would otherwise
        // throw `each_key_duplicate`.
        if (d.birdnet_id != null) return `bn:${d.birdnet_id}`;
        return `${d.timestamp}|${d.species}|${d.sensor_id ?? ''}|${index}`;
    }

    let audioDetections = $state<AudioDetection[]>([]);
    let pollInterval: ReturnType<typeof setInterval> | undefined;
    let summaryInterval: ReturnType<typeof setInterval> | undefined;
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

<section data-dashboard-audio class="flex h-full flex-col border-t border-slate-200 pt-5 dark:border-slate-700">
    <header class="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div class="flex items-center gap-3">
            <span class="flex h-9 w-9 items-center justify-center rounded-xl border border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-300" aria-hidden="true">
                <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M19 11a7 7 0 0 1-14 0m7 7v3m-4 0h8M9 5a3 3 0 0 1 6 0v6a3 3 0 0 1-6 0V5Z" /></svg>
            </span>
            <div>
                <div class="flex items-center gap-2">
                    <h3 class="font-display text-lg font-bold text-slate-950 dark:text-white">{$_('dashboard.audio_feed.title')}</h3>
                    {#if !loading && audioDetections.length > 0}
                        <span class="inline-flex items-center gap-1.5 text-xs font-semibold text-emerald-700 dark:text-emerald-300">
                            <span class="h-2 w-2 rounded-full bg-emerald-500" aria-hidden="true"></span>
                            {$_('dashboard.audio_feed.active')}
                        </span>
                    {/if}
                </div>
                <p class="text-sm text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.subtitle')}</p>
            </div>
        </div>
        <div class="flex flex-wrap items-center gap-1">
            <button
                data-audio-history-action
                type="button"
                class="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-sky-200 bg-sky-50/75 px-3.5 py-2 text-sm font-semibold text-sky-800 shadow-sm transition-colors hover:border-sky-300 hover:bg-sky-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-500 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-200 dark:hover:border-sky-700 dark:hover:bg-sky-950/65"
                title={$_('dashboard.audio_feed.open_history')}
                onclick={() => onNavigate?.('/audio')}
            >
                {$_('dashboard.audio_feed.open_history')}
                <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m9 5 7 7-7 7" /></svg>
            </button>
            {#if birdnetExternalUrl}
                <a
                    href={birdnetExternalUrl}
                    target="_blank"
                    rel="noopener noreferrer"
                    class="inline-flex min-h-11 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-teal-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-teal-300"
                    title={$_('dashboard.audio_feed.open_birdnet')}
                >
                    BirdNET-Go
                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14 5h5v5M19 5 10 14M5 7v12h12" /></svg>
                </a>
            {/if}
        </div>
    </header>

    {#if summary && summary.total > 0}
        <div class="mb-3 flex items-center gap-4 rounded-xl bg-slate-100/70 px-3 py-2.5 dark:bg-slate-900/45">
            <div class="flex items-baseline gap-1.5">
                <span class="font-display text-xl font-bold leading-none tabular-nums text-teal-700 dark:text-teal-300">{summary.total.toLocaleString()}</span>
                <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.heard_today')}</span>
            </div>
            <div class="h-6 w-px bg-slate-200 dark:bg-slate-700" aria-hidden="true"></div>
            <div class="flex items-baseline gap-1.5">
                <span class="font-display text-xl font-bold leading-none tabular-nums text-slate-800 dark:text-slate-100">{summary.species_count}</span>
                <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.species')}</span>
            </div>
            {#if sparkline.hasData}
                <svg viewBox="0 0 100 24" preserveAspectRatio="none" class="ml-auto h-6 w-24 shrink-0 overflow-visible" aria-hidden="true">
                    <polyline points={sparkline.area} fill="currentColor" class="text-teal-500/15" stroke="none" />
                    <polyline points={sparkline.points} fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round" class="text-teal-500 dark:text-teal-400" vector-effect="non-scaling-stroke" />
                </svg>
            {/if}
        </div>
    {/if}

    <div data-dashboard-audio-list class="flex-1 divide-y divide-slate-200 overflow-hidden rounded-2xl bg-slate-50/75 ring-1 ring-slate-200/80 dark:divide-slate-700 dark:bg-slate-900/35 dark:ring-slate-700/70">
        {#if loading}
            {#each Array.from({ length: RECENT_AUDIO_LIMIT }) as _}
                <div class="h-16 animate-pulse bg-slate-100/70 dark:bg-slate-800/40"></div>
            {/each}
        {:else if audioDetections.length === 0}
            <div class="flex min-h-40 flex-col items-center justify-center px-4 py-8 text-center">
                <span class="mb-3 flex h-11 w-11 items-center justify-center rounded-full bg-slate-100 text-slate-400 dark:bg-slate-800">
                    <svg class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M5.586 15H4a1 1 0 0 1-1-1v-4a1 1 0 0 1 1-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
                </span>
                <p class="text-sm font-semibold text-slate-600 dark:text-slate-300">{$_('dashboard.audio_feed.empty_title')}</p>
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.empty_subtitle')}</p>
            </div>
        {:else}
            {#each audioDetections as detection, i (detectionKey(detection, i))}
                {@const spec = spectrogramUrl(detection.birdnet_id)}
                {@const link = birdnetDetectionUrl(detection.birdnet_id)}
                {#snippet body()}
                    {#if spec}
                        <img src={spec} alt="" aria-hidden="true" loading="lazy" class="pointer-events-none absolute inset-0 h-full w-full select-none object-cover opacity-45 dark:opacity-35" />
                        <div class="absolute inset-0 bg-gradient-to-r from-white/95 via-white/72 to-white/35 dark:from-slate-900/95 dark:via-slate-900/72 dark:to-slate-900/40"></div>
                    {/if}
                    <div class="relative flex min-h-16 items-center justify-between gap-4 px-3 py-3">
                        <div class="min-w-0">
                            <p class="truncate text-sm font-semibold text-slate-900 dark:text-white">{detection.species}</p>
                            <p class="mt-1 flex flex-wrap items-center gap-x-2 text-xs text-slate-500 dark:text-slate-400">
                                <span>{formatTimeWithSeconds(detection.timestamp)}</span>
                                <span aria-hidden="true">·</span>
                                <span class="truncate">{detection.sensor_id || $_('dashboard.audio_feed.unknown_sensor')}</span>
                            </p>
                        </div>
                        <span class="inline-flex shrink-0 items-center gap-1.5 text-sm font-bold tabular-nums {detection.confidence > 0.7 ? 'text-emerald-700 dark:text-emerald-300' : 'text-amber-700 dark:text-amber-300'}">
                            <span class="h-2 w-2 rounded-full {detection.confidence > 0.7 ? 'bg-emerald-500' : 'bg-amber-500'}" aria-hidden="true"></span>
                            {(detection.confidence * 100).toFixed(0)}%
                        </span>
                    </div>
                {/snippet}
                {#if link}
                    <a href={link} target="_blank" rel="noopener noreferrer" class="relative block min-h-16 overflow-hidden transition-colors hover:bg-teal-50/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-teal-500 dark:hover:bg-teal-950/20" title={$_('dashboard.audio_feed.open_in_birdnet')}>
                        {@render body()}
                    </a>
                {:else}
                    <div class="relative min-h-16 overflow-hidden">{@render body()}</div>
                {/if}
            {/each}
        {/if}
    </div>
</section>
