<script lang="ts">
    import type { DeskWindowKind } from '../utils/desk-window';
    import { onMount, onDestroy, untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchRecentAudio, type AudioDetection, type AudioSummaryResponse } from '../api';
    import { REFRESH_CADENCE_MS } from '../app/refresh-cadence';
    import { startLiveReading, type LiveReading } from '../app/live-reading';
    import { audioActivity } from '../stores/audio_activity.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import { guestRecentAudioPollDelayMs } from '../app/public-refresh-budget';
    import { createObservationProjectionLoader } from '../app/observation-projection-loader';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    /**
     * What the microphone heard over the window: how many species, the species heard most and the
     * latest call. The day bar carries the call and cross-confirmation totals, so they are not
     * repeated here. The raw call-by-call feed lives on the audio history page; this card summarises. The window's summary is the Dashboard's, shared
     * with the day bar; the latest call is polled here within the guest refresh budget.
     */
    let {
        onNavigate,
        summary,
        summaryLoading,
        matchedCalls = null,
        summaryFailed = false,
        windowKind = 'rolling'
    }: {
        onNavigate?: (path: string) => void;
        summary: AudioSummaryResponse | null;
        summaryLoading: boolean;
        matchedCalls?: number | null;
        /** The latest read of the summary failed, so a missing summary is not "nothing heard". */
        summaryFailed?: boolean;
        /** The Dashboard's window, which the summary was read for. */
        windowKind?: DeskWindowKind;
    } = $props();

    const RECENT_AUDIO_LIMIT = 1;
    const MOST_HEARD_LIMIT = 4;
    const RECENT_AUDIO_POLL_MS = REFRESH_CADENCE_MS.recentAudio;


    let audioDetections = $state<AudioDetection[]>([]);
    let loading = $state(true);
    let birdnetExternalUrl = $state('');


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

    /** True when the latest call was read, so a failed read is retried instead of taken as fresh. */
    async function loadAudio(): Promise<boolean> { return audioLoader.load(); }

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => {
            loading = true;
            audioLoader.invalidate();
            void audioLoader.load();
        });
    });

    async function loadBirdnetUrl() {
        if (!authStore.showSettings) {
            birdnetExternalUrl = '';
            return;
        }
        try {
            const settings = await settingsStore.read();
            birdnetExternalUrl = settings.birdnet_external_url || settings.birdnet_url || '';
        } catch {
            birdnetExternalUrl = '';
        }
    }



    // The owner's live stream announces every new call, so the card reads when one is heard
    // instead of every 15 seconds; a guest, or an owner whose stream is down, polls as before.
    const followsLiveStream = $derived(authStore.hasOwnerAccess && detectionsStore.connected);
    let latestCallReading: LiveReading | undefined;

    onMount(() => {
        latestCallReading = startLiveReading({
            read: loadAudio,
            live: () => followsLiveStream,
            pollMs: () => authStore.isGuest
                ? guestRecentAudioPollDelayMs(authStore.publicAccessRateLimitPerMinute)
                : RECENT_AUDIO_POLL_MS,
            quietMs: REFRESH_CADENCE_MS.liveSafetyRead
        });
        void loadBirdnetUrl();
    });

    let handledAudioActivity = audioActivity.version;
    $effect(() => {
        const version = audioActivity.version;
        if (version === handledAudioActivity) return;
        handledAudioActivity = version;
        latestCallReading?.changed();
    });

    $effect(() => {
        void followsLiveStream;
        latestCallReading?.liveChanged();
    });

    onDestroy(() => {
        latestCallReading?.stop();
        audioLoader.dispose();
    });

    const latestCall = $derived(audioDetections[0] ?? null);
    const mostHeard = $derived((summary?.top_species ?? []).slice(0, MOST_HEARD_LIMIT));
    const mostHeardMax = $derived(Math.max(1, ...mostHeard.map((item) => item.count)));
</script>

<section data-dashboard-audio class="panel space-y-4" aria-labelledby="dashboard-heard-title">
    <div>
        <h2 id="dashboard-heard-title" class="flex items-center gap-2 font-display text-xl font-bold text-strong">
            <svg class="h-5 w-5 text-accent-ink" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <rect x="9" y="3" width="6" height="11" rx="3" />
                <path stroke-linecap="round" d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            </svg>
            {$_('dashboard.desk.heard_title', { default: 'Heard' })}
        </h2>
        <p class="mt-0.5 text-sm text-muted">{windowKind === 'today' ? $_('dashboard.day_bar.window_today', { default: 'Today' }) : $_('dashboard.day_bar.window', { default: 'Last 24 hours' })}</p>
    </div>

    {#if (loading || summaryLoading) && !summary}
        <div class="h-24 animate-pulse rounded-lg bg-surface-raised"></div>
    {:else if !summary && summaryFailed}
        <p class="text-xs text-muted" data-dashboard-heard-unavailable>
            {$_('dashboard.desk.heard_unavailable', { default: 'Calls heard could not be loaded. The dashboard tries again every minute.' })}
        </p>
    {:else if !summary || summary.total === 0}
        <p class="text-xs text-muted">{windowKind === 'today' ? $_('dashboard.desk.heard_empty_today', { default: 'No calls heard yet today.' }) : $_('dashboard.desk.heard_empty', { default: 'No calls heard in the last 24 hours.' })}</p>
    {:else}
        <!-- The day bar already carries calls heard and cross-confirmed; this card says what was heard. -->
        <p class="font-display text-lg font-bold text-strong" data-dashboard-species-heard>
            {$_('dashboard.desk.species_heard', {
                values: { count: summary.species_count },
                default: '{count, plural, one {# species heard} other {# species heard}}'
            })}
        </p>

        {#if mostHeard.length > 0}
            <div class="space-y-1.5" data-dashboard-most-heard>
                <p class="text-xs font-semibold text-muted">{$_('dashboard.desk.most_heard', { default: 'Heard most' })}</p>
                <ol class="space-y-1.5">
                    {#each mostHeard as item, index (`${item.species}|${index}`)}
                        <li class="space-y-1">
                            <div class="flex items-baseline justify-between gap-3 text-sm">
                                <span class="min-w-0 wrap-break-word text-strong">{item.species}</span>
                                <span class="shrink-0 tabular-nums text-muted">{item.count.toLocaleString()}</span>
                            </div>
                            <div class="h-1 overflow-hidden rounded-full bg-track" aria-hidden="true">
                                <div class="h-full rounded-full bg-status-info-line" style:width="{Math.max(2, (item.count / mostHeardMax) * 100)}%"></div>
                            </div>
                        </li>
                    {/each}
                </ol>
            </div>
        {/if}

        {#if latestCall}
            <p class="text-xs text-muted" data-dashboard-latest-call>
                {$_('dashboard.desk.latest_call', {
                    values: { species: latestCall.species, time: formatTime(latestCall.timestamp) },
                    default: 'Latest call: {species} at {time}'
                })}
            </p>
        {/if}

        {#if matchedCalls === 0}
            <p class="text-xs leading-relaxed text-muted" data-dashboard-no-match>
                {$_('dashboard.desk.no_cross_confirmation', {
                    values: { count: summary.total },
                    default:
                        '{count, plural, one {# call was heard but it did not line up with a camera visit.} other {# calls were heard but none lined up with a camera visit.}} The microphone and the cameras may be covering different ground.'
                })}
            </p>
        {/if}
    {/if}

    <div class="flex flex-wrap items-center gap-2">
        <button
            data-audio-history-action
            type="button"
            class="btn btn-secondary min-h-11 px-4 text-xs"
            onclick={() => onNavigate?.('/audio')}
        >
            {$_('dashboard.audio_feed.open_history')}
        </button>
        {#if birdnetExternalUrl}
            <a
                href={birdnetExternalUrl}
                target="_blank"
                rel="noopener noreferrer"
                class="inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 text-xs font-semibold text-muted transition-colors hover:bg-surface-raised hover:text-accent-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus"
                title={$_('dashboard.audio_feed.open_birdnet')}
            >
                BirdNET-Go
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M14 5h5v5M19 5 10 14M5 7v12h12" /></svg>
            </a>
        {/if}
    </div>
</section>
