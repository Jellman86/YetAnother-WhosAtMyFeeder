<script lang="ts">
    import { fetchVisits } from '../api/visits';
    import { onMount, untrack } from 'svelte';
    import LazyModal from '../components/LazyModal.svelte';
    import {
        loadDetectionModal,
        loadGardenCaptureModal,
        loadReviewQueueModal,
        loadSpeciesDetailModal,
        loadVideoPlayer
    } from '../components/lazy-dialogs';
    import DailyHistogram from '../components/DailyHistogram.svelte';
    import TopVisitors from '../components/TopVisitors.svelte';
    import FieldLog from '../components/FieldLog.svelte';
    import { fetchGardenVisits, type GardenServerVisit } from '../api/garden';
    import { gardenHistory } from '../stores/garden_history.svelte';
    import { GardenVisitViewer } from '../utils/garden-visit-viewer.svelte';
    import { mergeFieldLog } from '../utils/field-log';
    import NotableNearby from '../components/NotableNearby.svelte';
    import ReviewQueueCard from '../components/ReviewQueueCard.svelte';
    import ProviderWarning from '../components/ProviderWarning.svelte';
    import DayBar from '../components/DayBar.svelte';
    import DeskContextCards from '../components/DeskContextCards.svelte';
    import RecentAudio from '../components/RecentAudio.svelte';
    import { createObservationProjectionLoader } from '../app/observation-projection-loader';
    import { detectionsStore } from '../stores/detections.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import type { AudioSummaryResponse, Detection, DailySummary } from '../api';
    import { deleteDetection, hideDetection, updateDetectionSpecies, fetchAudioSummary, fetchDailySummary, reclassifyDetection, fetchNewSpeciesQueue, updateSettings } from '../api';
    import { settingsStore } from '../stores/settings.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { fullVisitStore } from '../stores/full-visit.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { guestRecentAudioPollDelayMs } from '../app/public-refresh-budget';
    import { _ } from 'svelte-i18n';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';
    import { selectReclassificationStrategy } from '../utils/reclassification';

    import { fromServerVisit, withinDeskWindow } from '../utils/visit-grouping';
    import { buildReviewQueue, type NewSpeciesEntry } from '../utils/review-queue';
    import { applyManualTagResult } from '../utils/manual-tag';

    interface Props {
        onnavigate?: (path: string) => void;
    }

    let { onnavigate }: Props = $props();

    /** The dashboard shows the recent slice of the day; Explorer holds the full history. */
    const VISIT_ROW_LIMIT = 12;
    let serverVisits = $state<ReturnType<typeof fromServerVisit>[]>([]);
    let totalVisits = $state(0);

    // Garden captures are beta, and visitors see confirmed animals; animals stay a separate record no bird total counts.
    const gardenAvailable = $derived(
        (authStore.hasOwnerAccess && settingsStore.settings?.beta_garden_animals === true) || authStore.guestCanViewGarden
    );
    let gardenVisits = $state.raw<GardenServerVisit[]>([]);
    let gardenTotal = $state(0);
    let gardenUnavailable = $state(false);
    let gardenWindow = $state.raw<{ start: string; end: string } | null>(null);
    const gardenScope = $derived({ start: gardenWindow?.start ?? null, end: gardenWindow?.end, status: 'reviewable' as const });
    const gardenViewer = new GardenVisitViewer(
        () => gardenScope,
        () => $_('garden.save_error', { default: 'Could not save your review. Try again.' })
    );

    let summary = $state<DailySummary | null>(null);
    // The clock hour the summary's rolling window ended in, so the activity chart ends where its data does.
    let summaryHour = $state(new Date().getHours());
    let summaryLoading = $state(true);
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let notableRefreshKey = $state(0);
    let lastModalEventId = $state<string | null>(null);

    const birdnetEnabled = $derived(
        (settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false) && authStore.canViewAudio
    );

    // Video playback state
    let showVideo = $state(false);
    let videoEventId = $state<string | null>(null);
    let videoPlayIntent = $state<'auto' | 'user'>('auto');
    let fullVisitAvailability = $derived(fullVisitStore.availability);
    let fullVisitFetchState = $derived(fullVisitStore.fetchState);
    let recordingClipFetchEnabled = $derived(
        (settingsStore.settings?.recording_clip_enabled ?? false) &&
        (settingsStore.settings?.clips_enabled ?? false)
    );
    let selectedEventFullVisitHandler = $derived.by(() => {
        const current = selectedEvent;
        if (!current || !recordingClipFetchEnabled) return undefined;
        return () => handleFetchFullVisit(current);
    });

    /** Opening a record closes any video still playing, so one overlay is shown at a time. */
    function openRecord(detection: Detection): void {
        showVideo = false;
        selectedEvent = detection;
    }

    // One window for the whole desk, so the day bar, the log and the context cards agree.
    let deskDetections = $derived(withinDeskWindow(detectionsStore.detections));
    let reviewThreshold = $derived(settingsStore.settings?.classification_threshold ?? null);

    // The day reads as visits, not frames: repeat frames of one bird fold into one row, and a
    // Garden animal's visit sits on the same thread between them.
    let allVisits = $derived(serverVisits);
    let fieldLogRows = $derived(mergeFieldLog(allVisits, gardenVisits, VISIT_ROW_LIMIT));
    let visits = $derived(fieldLogRows.flatMap((row) => (row.kind === 'visit' ? [row.visit] : [])));
    let hiddenVisitCount = $derived(Math.max(totalVisits + gardenTotal - fieldLogRows.length, 0));

    // Reviewing is an owner capability: the identify and hide calls require it, so a guest
    // must not be shown the queue, the walk-through, or an Identify button that would 403.
    let canReview = $derived(authStore.hasOwnerAccess);

    // The walk-through flow: a captured queue worked one at a time.
    let reviewSessionOpen = $state(false);

    $effect(() => {
        if (!canReview) reviewSessionOpen = false;
    });

    async function identifyFromQueue(detection: Detection, species: string): Promise<void> {
        try {
            const result = await updateDetectionSpecies(detection.frigate_event, species);
            detectionsStore.recordOwnerSpeciesChoice(applyManualTagResult(detection, result));
            toastStore.show($_('detection.species_updated', { default: 'Species updated' }), 'success');
            void refreshNewSpecies();
        } catch (e) {
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    async function hideFromQueue(detection: Detection): Promise<void> {
        try {
            await hideDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            void refreshNewSpecies();
        } catch (e) {
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    async function deleteFromQueue(detection: Detection): Promise<void> {
        try {
            await deleteDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            void refreshNewSpecies();
            await loadSummary();
        } catch (e) {
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    async function blockFromQueue(detection: Detection): Promise<void> {
        try {
            const existing = settingsStore.settings?.blocked_species ?? [];
            await updateSettings({
                blocked_species: [
                    ...existing,
                    {
                        scientific_name: detection.scientific_name ?? null,
                        common_name: detection.common_name ?? detection.display_name,
                        taxa_id: detection.taxa_id ?? null
                    }
                ]
            });
            await settingsStore.load();
            toastStore.show(
                $_('dashboard.review_session.species_blocked', {
                    values: { species: detection.display_name },
                    default: '{species} blocked. Future detections will be dropped.'
                }),
                'success'
            );
            void refreshNewSpecies();
        } catch (e) {
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    // Each unconfirmed new species' latest sighting, asking for one human call (#310).
    let newSpeciesEntries = $state<NewSpeciesEntry[]>([]);
    async function refreshNewSpecies(): Promise<void> {
        if (!canReview) {
            newSpeciesEntries = [];
            return;
        }
        try {
            const res = await fetchNewSpeciesQueue();
            newSpeciesEntries = res.items.map((item) => ({
                detection: item as unknown as Detection,
                sightings: item.species_sightings
            }));
        } catch {
            newSpeciesEntries = [];
        }
    }

    $effect(() => {
        void canReview;
        void refreshNewSpecies();
    });

    // Detections still waiting on a person, oldest first.
    let reviewQueue = $derived(buildReviewQueue(deskDetections, { reviewThreshold, newSpecies: newSpeciesEntries, knownDetections: detectionsStore.detections, localChoices: detectionsStore.patchMap }));

    $effect(() => {
        if (!recordingClipFetchEnabled) return;
        for (const visit of visits) {
            void fullVisitStore.ensureAvailability(visit.best.frigate_event);
        }
    });

    $effect(() => {
        if (!recordingClipFetchEnabled || !selectedEvent) {
            return;
        }
        const eventId = selectedEvent.frigate_event;
        const isNewOpen = eventId !== lastModalEventId;
        if (isNewOpen) {
            lastModalEventId = eventId;
            // Force fresh probe: a cached 'unavailable' from a previous check may
            // now be wrong if the clip was fetched in another session or tab.
            void fullVisitStore.ensureAvailability(eventId, { refresh: true, autoFetch: true });
        } else {
            // Same event still open (SSE update to selectedEvent while modal is open).
            // Non-refresh probe respects the current cache — no redundant round-trips.
            void fullVisitStore.ensureAvailability(eventId, { autoFetch: true });
        }
    });

    function detectionSyncSignature(d: Detection): string {
        const asText = (value: unknown) => {
            if (value === null || value === undefined) return '';
            return String(value);
        };
        const asNumber = (value: unknown) => {
            const parsed = Number(value);
            return Number.isFinite(parsed) ? String(parsed) : '';
        };
        const asFlag = (value: unknown) => (value ? '1' : '0');
        return [
            asText(d.frigate_event),
            asText(d.display_name),
            asNumber(d.score),
            asFlag(d.manual_tagged),
            asFlag(d.is_hidden),
            asFlag(d.is_favorite),
            asText(d.video_classification_status),
            asText(d.video_classification_label),
            asNumber(d.video_classification_score),
            asText(d.ai_analysis),
            asText(d.ai_analysis_timestamp),
            JSON.stringify(d.bird_summary ?? null),
        ].join('|');
    }

    // Visits, as the log counts them. The summary counts the whole window; until it arrives the
    // loaded visits stand in, never the frame count, which is a different unit.
    let last24hCount = $derived(summary?.visit_count ?? allVisits.length);
    let last24hSpecies = $derived(summary?.top_species.length ?? 0);
    let audioConfirmations = $derived(summary?.audio_confirmations ?? 0);

    const summaryLoader = createObservationProjectionLoader({
        fetch: async (signal) => {
            const now = new Date();
            const window = { startTime: new Date(now.getTime() - 24 * 60 * 60 * 1000).toISOString(), endTime: now.toISOString() };
            // A Garden failure is stated beside the birds rather than taking the whole log down.
            const gardenRead = gardenAvailable
                ? fetchGardenVisits({ start: window.startTime, end: window.endTime, order: 'newest', limit: VISIT_ROW_LIMIT }, signal)
                    .then((page) => ({ page }), (error: unknown) => {
                        if (signal.aborted) throw error;
                        logger.warn('Garden visits unavailable for the field log', { message: getErrorMessage(error) });
                        return { page: null };
                    })
                : Promise.resolve(null);
            const [summaryRes, visitsRes, gardenRes] = await Promise.all([
                fetchDailySummary(),
                fetchVisits({ ...window, limit: VISIT_ROW_LIMIT, signal, requestKey: 'dashboard:visits' }),
                gardenRead
            ]);
            return { summaryRes, visitsRes, gardenRes, window };
        },
        apply: ({ summaryRes, visitsRes, gardenRes, window }) => {
            summary = summaryRes; summaryHour = new Date().getHours();
            serverVisits = visitsRes.visits.map((visit) => fromServerVisit(visit, window)); totalVisits = visitsRes.total;
            gardenWindow = { start: window.startTime, end: window.endTime };
            gardenUnavailable = gardenRes !== null && gardenRes.page === null;
            if (gardenRes === null) { gardenVisits = []; gardenTotal = 0; }
            else if (gardenRes.page) { gardenVisits = gardenRes.page.visits; gardenTotal = gardenRes.page.total; }
        },
        clear: () => { summary = null; serverVisits = []; totalVisits = 0; gardenVisits = []; gardenTotal = 0; gardenUnavailable = false; },
        fail: (e) => {
            if (authStore.isGuest) summary = null;
            if (isTransientRequestError(e)) {
                logger.warn('Dashboard summary fetch failed (transient)', { message: getErrorMessage(e) });
            } else {
                logger.error('Failed to load summary', e);
            }
        },
        settled: () => { summaryLoading = false; }
    });

    async function loadSummary() {
        // A retry after a failed first read is loading again, not still failed.
        if (summary === null) summaryLoading = true;
        await summaryLoader.load();
    }

    // Until the day has been read, its figures are unknown rather than zero.
    let summaryPending = $derived(summary === null && summaryLoading);
    let summaryUnavailable = $derived(summary === null && !summaryLoading);
    let queueStatus = $derived<'loading' | 'ready' | 'unavailable'>(
        detectionsStore.historyStatus === 'ready'
            ? 'ready'
            : detectionsStore.historyStatus === 'failed' && !detectionsStore.isLoading
              ? 'unavailable'
              : 'loading'
    );

    const SUMMARY_POLL_MS = 60_000;

    onMount(() => {
        void loadSummary();
        const interval = setInterval(() => { if (document.visibilityState === 'visible') void loadSummary(); }, SUMMARY_POLL_MS);
        // The day bar and the Heard card share this one reading, kept within a visitor's request budget.
        const audioPollMs = authStore.isGuest
            ? Math.max(SUMMARY_POLL_MS, guestRecentAudioPollDelayMs(authStore.publicAccessRateLimitPerMinute))
            : SUMMARY_POLL_MS;
        const audioInterval = setInterval(() => {
            if (document.visibilityState === 'visible' && birdnetEnabled) void audioSummaryLoader.load();
        }, audioPollMs);
        return () => { clearInterval(interval); clearInterval(audioInterval); summaryLoader.dispose(); audioSummaryLoader.dispose(); };
    });

    // Turning Garden on or off, or signing in as the owner, changes what the log may hold.
    let readGardenAvailable = untrack(() => gardenAvailable);
    $effect(() => {
        const available = gardenAvailable;
        if (available === readGardenAvailable) return;
        readGardenAvailable = available;
        if (!available) gardenViewer.close();
        untrack(() => { void loadSummary(); });
    });

    // A Garden review here or elsewhere changes the log's rows; quick successive changes read once.
    let handledGardenHistory = gardenHistory.version;
    $effect(() => {
        const version = gardenHistory.version;
        if (version === handledGardenHistory || !gardenAvailable) return;
        handledGardenHistory = version;
        const timer = setTimeout(() => { void loadSummary(); }, 350);
        return () => clearTimeout(timer);
    });

    function gardenGroupDismissed(ids: string[], skipped: number): void {
        gardenHistory.invalidate();
        gardenViewer.close();
        void loadSummary();
        const message = $_('garden.batch_dismissed', { default: '{count} photos dismissed.', values: { count: ids.length } });
        if (skipped > 0) {
            toastStore.warning(`${message} ${$_('garden.batch_skipped', { default: '{count} photos were unchanged because their review or availability changed.', values: { count: skipped } })}`);
        } else {
            toastStore.success(message);
        }
    }

    let handledVisitMutation = detectionsStore.mutationVersion;
    $effect(() => {
        const version = detectionsStore.mutationVersion;
        if (version <= handledVisitMutation) return;
        handledVisitMutation = version;
        const timeout = setTimeout(() => { void loadSummary(); }, 2000);
        return () => clearTimeout(timeout);
    });

    // What the microphone heard: the day bar's call count and the Heard card read this one summary.
    let audioSummary = $state.raw<AudioSummaryResponse | null>(null);
    let audioSummaryLoading = $state(true);

    const audioSummaryLoader = createObservationProjectionLoader({
        fetch: (signal) => fetchAudioSummary({ days: 1 }, signal),
        apply: (value) => { audioSummary = value; },
        clear: () => { audioSummary = null; },
        fail: (e) => {
            if (authStore.isGuest) audioSummary = null;
            if (isTransientRequestError(e)) {
                logger.warn('Audio summary unavailable (transient)', { message: getErrorMessage(e) });
            } else {
                logger.error('Failed to fetch audio summary', e);
            }
        },
        settled: () => { audioSummaryLoading = false; }
    });

    $effect(() => {
        if (!birdnetEnabled) { audioSummaryLoader.invalidate(); return; }
        untrack(() => { void audioSummaryLoader.load(); });
        return () => audioSummaryLoader.dispose();
    });

    let handledPublicHistoryVersion = detectionsStore.publicHistoryVersion;
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        if (version <= handledPublicHistoryVersion || !authStore.isGuest) return;
        handledPublicHistoryVersion = version;
        untrack(() => {
            summaryLoading = true;
            audioSummaryLoading = true;
            summaryLoader.invalidate();
            audioSummaryLoader.invalidate();
            void loadSummary();
            if (birdnetEnabled) void audioSummaryLoader.load();
        });
    });

    $effect(() => {
        return pageRefreshAction.register(async () => {
            summaryLoading = true;
            notableRefreshKey += 1;
            await Promise.all([
                detectionsStore.loadInitial(),
                loadSummary()
            ]);
        });
    });

    $effect(() => {
        if (!selectedEvent) return;
        const updated = detectionsStore.detections.find(
            (d) => d.frigate_event === selectedEvent?.frigate_event
        );
        // Avoid proxy-identity churn causing a self-triggering effect loop.
        if (updated) {
            const definedPatch = Object.fromEntries(
                Object.entries(updated).filter(([, value]) => value !== undefined)
            ) as Partial<Detection>;
            const merged = { ...selectedEvent, ...definedPatch } as Detection;
            if (detectionSyncSignature(merged) !== detectionSyncSignature(selectedEvent)) {
                selectedEvent = merged;
            }
        }
    });

    async function handleReclassify() {
        if (!selectedEvent) return;
        const eventId = selectedEvent.frigate_event;
        const requestedStrategy = selectReclassificationStrategy(
            selectedEvent.has_clip,
            fullVisitFetchState[eventId]
        );
        try {
            const result = await reclassifyDetection(eventId, requestedStrategy);

            if (result.status === 'queued') return;
            if (!result.updated) {
                toastStore.warning($_('notifications.reclassify_no_result'));
                return;
            }

            // Check if backend used a different strategy (fallback occurred)
            if (result.actual_strategy && result.actual_strategy !== requestedStrategy) {
                toastStore.warning($_('notifications.reclassify_fallback'));
            }
        } catch (error) {
            detectionsStore.dismissReclassification(eventId);
            const message = getErrorMessage(error);
            console.error('Failed to start reclassification', message, error);
            toastStore.error($_('notifications.reclassify_failed', { values: { message } }));
        }
    }

    async function handleFetchFullVisit(detection: Detection) {
        try {
            const complete = await fullVisitStore.fetchFullVisit(detection.frigate_event);
            if (complete) {
                toastStore.success($_('video_player.full_visit_ready', { default: 'Full visit clip ready' }));
            } else {
                toastStore.warning($_('video_player.partial_visit_ready', { default: 'A partial visit is ready; retry shortly for the complete clip.' }));
            }
        } catch (e) {
            const message = e instanceof Error ? e.message : $_('video_player.full_visit_failed', { default: 'Could not fetch full visit clip' });
            toastStore.error(message);
        }
    }

    function handleSpeciesSummaryClick(speciesFilter: string) {
        // Top Visitors is last-24h data; avoid forcing "today" which can hide valid events
        // around midnight boundaries. Filter by species/taxa only.
        onnavigate?.(`/events?species=${encodeURIComponent(speciesFilter)}`);
    }

    /** A bird correction, exclusion or recount changes the day's total and the log's summaries. */
    function handleBirdsChanged(): void {
        void loadSummary();
        void detectionsStore.refreshAfterOwnerEdit();
    }
</script>

<div class="space-y-6">
    <DayBar
        visitCount={summary ? last24hCount : null}
        countedBirds={summary?.counted_birds ?? 0}
        countedCaptures={summary?.counted_captures ?? 0}
        speciesCount={summary ? last24hSpecies : null}
        unresolvedCount={queueStatus === 'ready' || reviewQueue.total > 0 ? reviewQueue.total : null}
        audioCalls={audioSummary?.total ?? null}
        {audioConfirmations}
        loading={summaryPending || queueStatus === 'loading'}
        connected={detectionsStore.connected}
    />

    <ProviderWarning {onnavigate} />

    <!-- Field desk: the day reads as one chronological log beside a rail. Below 1920px the rail is one
         column; from there it splits in two, what needs you and what is happening beside the
         reference, so the log keeps a readable row instead of stretching across a wide screen. -->
    <section
        data-dashboard-field-desk
        class="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.75fr)] 3xl:grid-cols-[minmax(0,1.4fr)_minmax(0,2fr)]"
    >
        <div class="min-w-0" data-dashboard-field-log-column>
            <FieldLog
                rows={fieldLogRows}
                hiddenCount={hiddenVisitCount}
                loading={summaryPending}
                unavailable={summaryUnavailable}
                {gardenUnavailable}
                ongardenopen={(visit) => gardenViewer.open(visit)}
                {gardenScope}
                ongardencapture={(visit, capture, index) => gardenViewer.open(visit, { capture, index })}
                onretry={() => void loadSummary()}
                canIdentify={canReview}
                onselect={openRecord}
                onidentify={openRecord}
                onplay={(detection) => { videoEventId = detection.frigate_event; showVideo = true; }}
                onseeall={() => onnavigate?.(gardenVisits.length > 0 ? '/events?visitors=all' : '/events')}
            />
        </div>

        <aside class="grid min-w-0 grid-cols-1 items-start gap-6 3xl:grid-cols-2">
            <!-- What needs you, then what is happening now. -->
            <div class="flex min-w-0 flex-col gap-6" data-dashboard-rail-now>
                {#if canReview}
                    <ReviewQueueCard
                        queue={reviewQueue}
                        status={queueStatus}
                        onretry={() => void detectionsStore.loadInitial()}
                        onreview={openRecord}
                        onreviewall={() => (reviewSessionOpen = true)}
                    />
                {/if}

                <DeskContextCards
                    detections={deskDetections}
                    visits={allVisits}
                    cameraVisits={summary?.camera_visits ?? null}
                    loading={summaryPending}
                    unavailable={summaryUnavailable}
                />

                {#if birdnetEnabled}
                    <RecentAudio
                        onNavigate={onnavigate}
                        summary={audioSummary}
                        summaryLoading={audioSummaryLoading}
                        matchedCalls={summary ? audioConfirmations : null}
                    />
                {/if}
            </div>

            <!-- Reference: the shape of the day, the area around the feeder, who comes most. -->
            <div class="flex min-w-0 flex-col gap-6" data-dashboard-rail-reference>
                {#if summary}
                    <DailyHistogram data={summary.hourly_visits ?? []} currentHour={summaryHour} />
                {:else if summaryLoading}
                    <div class="h-40 animate-pulse rounded-2xl bg-surface-raised motion-reduce:animate-none"></div>
                {/if}

                <NotableNearby
                    canConfigure={canReview}
                    refreshKey={notableRefreshKey}
                    onconfigure={() => onnavigate?.('/settings/integrations')}
                    onselectspecies={(species) => (selectedSpecies = species)}
                />

                <div data-dashboard-top-visitors>
                    {#if summary}
                        <TopVisitors
                            species={summary.top_species}
                            onSpeciesClick={handleSpeciesSummaryClick}
                        />
                    {:else if summaryLoading}
                        <div class="h-40 animate-pulse rounded-2xl bg-surface-raised motion-reduce:animate-none"></div>
                    {/if}
                </div>
            </div>
        </aside>
    </section>
</div>

{#if reviewSessionOpen && canReview}
    {@const fullQueue = buildReviewQueue(deskDetections, {
        reviewThreshold,
        limit: Number.MAX_SAFE_INTEGER,
        newSpecies: newSpeciesEntries,
        knownDetections: detectionsStore.detections,
        localChoices: detectionsStore.patchMap
    })}
    <LazyModal loader={loadReviewQueueModal} onclose={() => (reviewSessionOpen = false)}>
        {#snippet children(ReviewQueueModal)}
            <ReviewQueueModal
                onbirdschanged={handleBirdsChanged}
                queue={fullQueue.items}
                reasons={fullQueue.reasons}
                onidentify={identifyFromQueue}
                onhide={hideFromQueue}
                onblock={blockFromQueue}
                ondelete={deleteFromQueue}
                onopen={(detection) => { reviewSessionOpen = false; openRecord(detection); }}
                onclose={() => (reviewSessionOpen = false)}
            />
        {/snippet}
    </LazyModal>
{/if}

<!-- Event Detail Modal -->
{#if selectedEvent}
    <LazyModal loader={loadDetectionModal} onclose={() => (selectedEvent = null)}>
        {#snippet children(DetectionModal)}
            {#if selectedEvent}
                <DetectionModal
                    onbirdschanged={handleBirdsChanged}
                    detection={selectedEvent}
                    llmReady={settingsStore.llmReady}
                    showVideoButton={true}
                    fullVisitAvailable={fullVisitAvailability[selectedEvent.frigate_event] === 'available'}
                    fullVisitFetched={fullVisitFetchState[selectedEvent.frigate_event] === 'ready'}
                    fullVisitFetchState={fullVisitFetchState[selectedEvent.frigate_event] ?? 'idle'}
                    onClose={() => selectedEvent = null}
                    onReclassify={handleReclassify}
                    onFetchFullVisit={selectedEventFullVisitHandler}
                    onPlayVideo={(frigateEvent: string, playIntent: 'auto' | 'user' = 'auto') => {
                        videoEventId = frigateEvent;
                        videoPlayIntent = playIntent;
                        showVideo = true;
                        selectedEvent = null;
                    }}
                    onViewSpecies={(species: string) => { selectedSpecies = species; selectedEvent = null; }}
                />
            {/if}
        {/snippet}
    </LazyModal>
{/if}

{#if gardenViewer.capture && gardenAvailable}
    <LazyModal loader={loadGardenCaptureModal} onclose={() => gardenViewer.close()}>
        {#snippet children(GardenCaptureModal)}
            {#if gardenViewer.capture}
                <GardenCaptureModal
                    capture={gardenViewer.capture}
                    group={gardenViewer.group?.items ?? [gardenViewer.capture]}
                    groupKind={gardenViewer.group?.kind ?? 'visit'}
                    groupTotal={gardenViewer.group?.captureCount ?? 1}
                    groupOffset={gardenViewer.offset}
                    groupLoading={gardenViewer.loading}
                    groupError={gardenViewer.error}
                    onpage={(index) => void gardenViewer.page(index)}
                    onclose={() => gardenViewer.close()}
                    onchanged={(next) => { gardenViewer.changed(next); void loadSummary(); }}
                    onselect={(capture) => (gardenViewer.capture = capture)}
                    ongroupdismissed={gardenGroupDismissed}
                />
            {/if}
        {/snippet}
    </LazyModal>
{/if}

{#if selectedSpecies}
    <LazyModal loader={loadSpeciesDetailModal} onclose={() => (selectedSpecies = null)}>
        {#snippet children(SpeciesDetailModal)}
            {#if selectedSpecies}<SpeciesDetailModal speciesName={selectedSpecies} onclose={() => selectedSpecies = null} />{/if}
        {/snippet}
    </LazyModal>
{/if}
{#if showVideo && videoEventId}
    <LazyModal loader={loadVideoPlayer} onclose={() => { showVideo = false; videoEventId = null; }}>
        {#snippet children(VideoPlayer)}
            {#if videoEventId}
                <VideoPlayer
                    frigateEvent={videoEventId}
                    playIntent={videoPlayIntent}
                    initialFullVisitPromoted={fullVisitFetchState[videoEventId] === 'ready'}
                    onClose={() => {
                        showVideo = false;
                        videoEventId = null;
                    }}
                />
            {/if}
        {/snippet}
    </LazyModal>
{/if}
