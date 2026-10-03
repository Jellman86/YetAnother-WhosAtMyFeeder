<script lang="ts">
    import { onMount, onDestroy, untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchRecentAudio, fetchAudioSummary, type AudioDetection, type AudioSummaryResponse } from '../api';
    import { fetchSettings } from '../api/settings';
    import { detectionsStore } from '../stores/detections.svelte';
    import { guestRecentAudioPollDelayMs } from '../app/public-refresh-budget';
    import { createObservationProjectionLoader } from '../app/observation-projection-loader';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    /**
     * What the microphone heard over the window: the totals, the species heard most, the latest
     * call, and how many camera visits a call confirmed. The raw call-by-call feed lives on the
     * audio history page; this card summarises, and keeps itself current by polling within the
     * guest refresh budget.
     */
    let { onNavigate, matchedCalls = null }: { onNavigate?: (path: string) => void; matchedCalls?: number | null } = $props();

    const RECENT_AUDIO_LIMIT = 1;
    const MOST_HEARD_LIMIT = 4;
    const RECENT_AUDIO_POLL_MS = 5_000;
    const AUDIO_SUMMARY_POLL_MS = 60_000;


    let audioDetections = $state<AudioDetection[]>([]);
    let pollTimer: ReturnType<typeof setTimeout> | undefined;
    let summaryTimer: ReturnType<typeof setTimeout> | undefined;
    let stopped = false;
    let loading = $state(true);
    let birdnetExternalUrl = $state('');
    let summary = $state<AudioSummaryResponse | null>(null);


    const audioLoader = createObservationProjectionLoader({
        fetch: (signal) => fetchRecentAudio(RECENT_AUDIO_LIMIT, signal),
        apply: (value) => { audioDetections = value; },
        clear: () => { audioDetections = []; },
        fail: (e) => {
            if (authStore.isGuest) audioDetections = [];
            if (isTransientRequestError(e)) logger.warn('Recent audio fetch failed (transient)', { message: getErrorMessage(e) });
            else logger.error('Failed to fetch recent audio', e);
        },
        settled: () => { loading = false; }
    });
    const summaryLoader = createObservationProjectionLoader({
        fetch: (signal) => fetchAudioSummary({ days: 1 }, signal),
        apply: (value) => { summary = value; },
        clear: () => { summary = null; },
        fail: (e) => {
            if (authStore.isGuest) summary = null;
            if (isTransientRequestError(e)) logger.warn('Audio summary fetch failed (transient)', { message: getErrorMessage(e) });
            else logger.error('Failed to fetch audio summary', e);
        }
    });

    async function loadAudio() { await audioLoader.load(); }
    async function loadSummary() { await summaryLoader.load(); }

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => {
            loading = true;
            audioLoader.invalidate();
            summaryLoader.invalidate();
            void audioLoader.load();
            void summaryLoader.load();
        });
    });

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



    function scheduleAudioPoll(delay = authStore.isGuest ? guestRecentAudioPollDelayMs(authStore.publicAccessRateLimitPerMinute) : RECENT_AUDIO_POLL_MS): void {
        if (stopped) return;
        if (pollTimer) clearTimeout(pollTimer);
        pollTimer = setTimeout(async () => {
            pollTimer = undefined;
            if (!document.hidden) {
                await loadAudio();
            }
            scheduleAudioPoll();
        }, delay);
    }

    function scheduleSummaryPoll(delay = authStore.isGuest ? Math.max(AUDIO_SUMMARY_POLL_MS, guestRecentAudioPollDelayMs(authStore.publicAccessRateLimitPerMinute)) : AUDIO_SUMMARY_POLL_MS): void {
        if (stopped) return;
        if (summaryTimer) clearTimeout(summaryTimer);
        summaryTimer = setTimeout(async () => {
            summaryTimer = undefined;
            if (!document.hidden) {
                await loadSummary();
            }
            scheduleSummaryPoll();
        }, delay);
    }

    onMount(() => {
        stopped = false;
        void loadAudio().finally(() => scheduleAudioPoll());
        void loadSummary().finally(() => scheduleSummaryPoll());
        void loadBirdnetUrl();
    });

    onDestroy(() => {
        stopped = true;
        audioLoader.dispose();
        summaryLoader.dispose();
        if (pollTimer) clearTimeout(pollTimer);
        if (summaryTimer) clearTimeout(summaryTimer);
    });

    const latestCall = $derived(audioDetections[0] ?? null);
    const mostHeard = $derived((summary?.top_species ?? []).slice(0, MOST_HEARD_LIMIT));
    const mostHeardMax = $derived(Math.max(1, ...mostHeard.map((item) => item.count)));
</script>

<section data-dashboard-audio class="space-y-3" aria-labelledby="dashboard-heard-title">
    <div>
        <h3 id="dashboard-heard-title" class="flex items-center gap-2 font-display text-sm font-bold text-slate-950 dark:text-white">
            <svg class="h-4 w-4 text-brand-600 dark:text-brand-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path stroke-linecap="round" d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
            {$_('dashboard.desk.heard_title', { default: 'Heard' })}
        </h3>
        <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.day_bar.window', { default: 'Last 24 hours' })}</p>
    </div>

    {#if loading && !summary}
        <div class="h-24 animate-pulse rounded-lg bg-slate-100/70 dark:bg-slate-800/40"></div>
    {:else if !summary || summary.total === 0}
        <p class="text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.desk.heard_empty', { default: 'No calls heard in the last 24 hours.' })}</p>
    {:else}
        <dl class="flex gap-6">
            <div>
                <dd class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white">{summary.total.toLocaleString()}</dd>
                <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.day_bar.calls_heard', { default: 'calls heard' })}</dt>
            </div>
            <div>
                <dd class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white">{summary.species_count.toLocaleString()}</dd>
                <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.audio_feed.species')}</dt>
            </div>
            {#if matchedCalls !== null}
                <div>
                    <dd class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white">{matchedCalls.toLocaleString()}</dd>
                    <dt class="text-xs text-slate-500 dark:text-slate-400">{$_('dashboard.day_bar.cross_confirmed', { default: 'cross-confirmed' })}</dt>
                </div>
            {/if}
        </dl>

        {#if mostHeard.length > 0}
            <div class="space-y-1.5" data-dashboard-most-heard>
                <p class="text-xs font-semibold text-slate-600 dark:text-slate-300">{$_('dashboard.desk.most_heard', { default: 'Heard most' })}</p>
                <ol class="space-y-1.5">
                    {#each mostHeard as item (item.species)}
                        <li class="space-y-1">
                            <div class="flex items-baseline justify-between gap-3 text-sm">
                                <span class="min-w-0 truncate text-slate-800 dark:text-slate-100">{item.species}</span>
                                <span class="shrink-0 tabular-nums text-slate-500 dark:text-slate-400">{item.count.toLocaleString()}</span>
                            </div>
                            <div class="h-1 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800" aria-hidden="true">
                                <div class="h-full rounded-full bg-brand-500/70 dark:bg-brand-400/70" style:width="{Math.max(2, (item.count / mostHeardMax) * 100)}%"></div>
                            </div>
                        </li>
                    {/each}
                </ol>
            </div>
        {/if}

        {#if latestCall}
            <p class="text-xs text-slate-500 dark:text-slate-400" data-dashboard-latest-call>
                {$_('dashboard.desk.latest_call', {
                    values: { species: latestCall.species, time: formatTime(latestCall.timestamp) },
                    default: 'Latest call: {species} at {time}'
                })}
            </p>
        {/if}

        {#if matchedCalls === 0}
            <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400" data-dashboard-no-match>
                {$_('dashboard.desk.no_cross_confirmation', {
                    values: { count: summary.total },
                    default:
                        '{count} calls were heard but none lined up with a camera visit. The microphone and the cameras may be covering different ground.'
                })}
            </p>
        {/if}
    {/if}

    <div class="flex flex-wrap items-center gap-2">
        <button
            data-audio-history-action
            type="button"
            class="btn btn-secondary min-h-11 rounded-full px-4 text-xs"
            onclick={() => onNavigate?.('/audio')}
        >
            {$_('dashboard.audio_feed.open_history')}
        </button>
        {#if birdnetExternalUrl}
            <a
                href={birdnetExternalUrl}
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800 dark:hover:text-brand-300"
                title={$_('dashboard.audio_feed.open_birdnet')}
            >
                BirdNET-Go
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14 5h5v5M19 5 10 14M5 7v12h12" /></svg>
            </a>
        {/if}
    </div>
</section>
