<script lang="ts">
    import { fetchVisits } from '../api/visits';
    import { settingsPartPath } from '../settings/settings-route';
    import { onMount, untrack } from 'svelte';
    import LazyModal from '../components/LazyModal.svelte';
    import { loadGardenCaptureModal, loadReviewQueueModal, loadSpeciesDetailModal } from '../components/lazy-dialogs';
    import DailyHistogram from '../components/DailyHistogram.svelte';
    import TopVisitors from '../components/TopVisitors.svelte';
    import FieldLog from '../components/FieldLog.svelte';
    import { fetchGardenVisits, type GardenServerVisit } from '../api/garden';
    import { gardenHistory } from '../stores/garden_history.svelte';
    import { GardenVisitViewer } from '../utils/garden-visit-viewer.svelte';
    import { fieldLogWindowLink, mergeFieldLog } from '../utils/field-log';
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
    import { deleteDetection, hideDetection, IdentificationChangedError, updateDetectionSpecies, fetchAudioSummary, fetchDailySummary, fetchReviewQueue, updateSettings, fetchLeaderboardSpecies, fetchAudioSpeciesLeaderboard } from '../api';
    import { readRangeCheck, speciesChecksLink, type RangeCheckReading } from '../leaderboard/species-checks';
    import { needsYourCall, type ReadingStatus, type SpeciesChecksView } from '../utils/needs-your-call';
    import type { DomesticBirdKey } from '../utils/domestic-birds';
    import { DomesticBirdOffers } from '../utils/domestic-bird-offers.svelte';
    import { birdNames } from '../naming';
    import { videoHeadingFor } from '../components/video-heading';
    import RecordDialogs from '../components/RecordDialogs.svelte';
    import { recordVisit, type RecordVisit } from '../components/record-visit';
    import type { RecordVideo } from '../components/record-video';
    import { canWatchRecordVideo, recordingClipsOn } from '../utils/record-access';
    import { settingsStore } from '../stores/settings.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { fullVisitStore } from '../stores/full-visit.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { guestRecentAudioPollDelayMs } from '../app/public-refresh-budget';
    import { REFRESH_CADENCE_MS } from '../app/refresh-cadence';
    import { startLiveReading, type LiveReading } from '../app/live-reading';
    import { createSingleFlightRunner } from '../app/single-flight';
    import { audioActivity } from '../stores/audio_activity.svelte';
    import { _ } from 'svelte-i18n';
    import { getErrorMessage, isTransientRequestError } from '../utils/error-handling';
    import { logger } from '../utils/logger';

    import { fromServerVisit, withinDeskWindow, type DetectionVisit as VisitGroup } from '../utils/visit-grouping';
    import {
        DayTurnedError,
        deskWindowStart,
        readOneDay,
        readDeskWindowChoice,
        saveDeskWindowChoice,
        narrowedToSharedDay,
        sharedHistoryStart,
        type DeskWindow,
        type DeskWindowKind
    } from '../utils/desk-window';
    import { msUntilNextLocalMidnight } from './audio-history-window';
    import { formatTime } from '../utils/datetime';
    import { buildReviewQueue, EMPTY_REVIEW_QUEUE_READING, readingFromResponse, withoutEvent, type ReviewQueueReading } from '../utils/review-queue';
    import { dayBarSlots } from '../utils/day-bar';
    import { liveFeedState } from '../utils/live-feed-state';
    import { serviceConnectionsStore } from '../stores/service_connections.svelte';
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

    // The window this device chose, and the window the figures on screen were read for. A new choice
    // clears every reading, so nothing read for one window is ever shown under the other's name.
    let windowChoice = $state<DeskWindowKind>(readDeskWindowChoice(() => localStorage));
    let shownWindow = $state.raw<DeskWindow | null>(null);
    const deskKind = $derived<DeskWindowKind>(shownWindow?.kind ?? windowChoice);
    // Advanced at local midnight while Today is chosen, so the live captures move to the new day too.
    let dayTurn = $state(0);
    // The local midnight the desk reads while Today is chosen. Every read is checked against it, so
    // one load never shows a new day's figures beside the old day's visits or calls.
    let readingDay = deskWindowStart('today', new Date());

    /** One read of the desk's window, never across two days (see `readOneDay`). */
    function readDeskDay<T>(
        read: (window: DeskWindow) => Promise<T>,
        countedFrom: (value: T) => readonly (string | null | undefined)[],
        consistent?: (value: T) => boolean
    ): Promise<{ value: T; window: DeskWindow }> {
        return readOneDay({ kind: windowChoice, day: windowChoice === 'today' ? readingDay : null, clock: () => new Date(), read, countedFrom, consistent });
    }

    let summary = $state<DailySummary | null>(null);
    // The clock hour the summary's window ended in, so the activity chart ends where its data does.
    let summaryHour = $state(new Date().getHours());
    let summaryLoading = $state(true);
    let selectedEvent = $state<Detection | null>(null);
    let selectedSpecies = $state<string | null>(null);
    let notableRefreshKey = $state(0);

    const birdnetEnabled = $derived(
        (settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false) && authStore.canViewAudio
    );

    let video = $state.raw<RecordVideo | null>(null);
    let recordingClipFetchEnabled = $derived(
        recordingClipsOn(settingsStore.settings, publicSettingsStore.settings) && canWatchRecordVideo(authStore)
    );

    // The visit a record was opened from, so the record can say it is one capture of that visit.
    let openedVisit = $state<RecordVisit | null>(null);

    /** Opening a record closes any video still playing, so one overlay is shown at a time. */
    function openRecord(detection: Detection, visit?: VisitGroup): void {
        video = null;
        openedVisit = recordVisit(detection.frigate_event, visit);
        selectedEvent = detection;
    }

    // One window for the whole desk, so the day bar, the log and the context cards agree. A capture
    // the live stream adds is kept only if it falls inside it: never yesterday's in Today.
    let deskDetections = $derived.by(() => {
        void dayTurn;
        const now = new Date();
        return withinDeskWindow(detectionsStore.detections, now.getTime(), deskWindowStart(deskKind, now));
    });
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
            // The queue shows a snapshot; the server applies this only while the visit still reads as shown.
            const result = await updateDetectionSpecies(detection.frigate_event, species, detection.category_name);
            detectionsStore.recordOwnerSpeciesChoice(applyManualTagResult(detection, result));
            toastStore.show($_('detection.species_updated', { default: 'Species updated' }), 'success');
            loadReviewQueue();
            void loadSummary();
        } catch (e) {
            if (e instanceof IdentificationChangedError) {
                // Changed elsewhere: say what it reads now, and show that rather than the old copy.
                detectionsStore.updateDetection({ ...detection, ...e.current });
                toastStore.show(e.message, 'info');
                loadReviewQueue();
                throw e;
            }
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    async function hideFromQueue(detection: Detection): Promise<void> {
        try {
            await hideDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            reviewReading = withoutEvent(reviewReading, detection.frigate_event);
            loadReviewQueue();
            void loadSummary();
        } catch (e) {
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    async function deleteFromQueue(detection: Detection): Promise<void> {
        try {
            await deleteDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            reviewReading = withoutEvent(reviewReading, detection.frigate_event);
            loadReviewQueue();
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
                    values: { species: $birdNames(detection, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary).primary },
                    default: '{species} blocked. It will not be recorded from now on.'
                }),
                'success'
            );
            loadReviewQueue();
        } catch (e) {
            toastStore.show(getErrorMessage(e), 'error');
            throw e;
        }
    }

    // What is waiting comes from the server, so it covers the whole day and every new species (#917)
    // rather than however much of the day still fits in the recent history.
    const REVIEW_QUEUE_READ_LIMIT = 8;
    const REVIEW_SESSION_READ_LIMIT = 500;
    const REVIEW_QUEUE_MIN_INTERVAL_MS = 15_000;
    let reviewReading = $state.raw<ReviewQueueReading>(EMPTY_REVIEW_QUEUE_READING);
    let reviewReadingStatus = $state<ReadingStatus>('loading');
    let lastReviewQueueRead = 0;
    // Whether each part of the day failed on its last read. Reads the view takes itself (the first,
    // and those after an edit or an announcement) are counted by the day's reading too, so a failure
    // is retried at the poll cadence instead of waiting for the five-minute safety read.
    const dayReadFailed = { summary: false, checks: false, queue: false };
    let daySafetyReading: LiveReading | undefined;
    function reportDayRead(): void {
        daySafetyReading?.report(!dayReadFailed.summary && !dayReadFailed.checks && !dayReadFailed.queue);
    }

    const reviewQueueLoader = createObservationProjectionLoader({
        // Needs your call waits on the captures of the desk's window, as the Unresolved figure counts them.
        fetch: (signal) => readDeskDay(
            (window) => fetchReviewQueue({ limit: REVIEW_QUEUE_READ_LIMIT, window: window.kind, signal }),
            (response) => [response.window_start]
        ),
        apply: ({ value: response }) => {
            reviewReading = readingFromResponse(response);
            reviewReadingStatus = 'ready';
            dayReadFailed.queue = false;
        },
        clear: () => {
            reviewReading = EMPTY_REVIEW_QUEUE_READING;
            reviewReadingStatus = 'loading';
        },
        fail: (e) => {
            if (e instanceof DayTurnedError) { rollOverIfNewDay(); return; }
            reviewReadingStatus = 'unavailable';
            dayReadFailed.queue = true;
            logger.warn('Review queue unavailable', { message: getErrorMessage(e) });
        },
        settled: () => reportDayRead()
    });
    function loadReviewQueue(): void {
        if (!canReview) return;
        lastReviewQueueRead = Date.now();
        void reviewQueueLoader.load();
    }
    function retryReviewQueue(): void {
        reviewReadingStatus = 'loading';
        loadReviewQueue();
    }

    $effect(() => {
        if (canReview) {
            untrack(loadReviewQueue);
            return;
        }
        reviewQueueLoader.invalidate();
        // A list read before signing out must not open itself at the next sign-in.
        reviewSessionRequest += 1;
    });

    let reviewQueue = $derived(buildReviewQueue(reviewReading, { reviewThreshold, knownDetections: detectionsStore.detections, localChoices: detectionsStore.patchMap }));

    // The walkthrough needs more than the card previews, so it reads its own list when opened.
    let reviewSessionReading = $state.raw<ReviewQueueReading>(EMPTY_REVIEW_QUEUE_READING);
    let reviewSessionOpening = false;
    let reviewSessionRequest = 0;
    // The walkthrough captures its list when it opens; a new list for a new day opens it afresh.
    let reviewSessionKey = $state(0);
    function readReviewSession(): Promise<ReviewQueueReading> {
        return readDeskDay(
            (window) => fetchReviewQueue({ limit: REVIEW_SESSION_READ_LIMIT, window: window.kind }),
            (response) => [response.window_start]
        ).then(({ value }) => readingFromResponse(value));
    }
    async function openReviewSession(): Promise<void> {
        if (reviewSessionOpening) return;
        reviewSessionOpening = true;
        const request = ++reviewSessionRequest;
        try {
            const reading = await readReviewSession();
            if (request !== reviewSessionRequest) return;
            reviewSessionReading = reading;
            reviewSessionOpen = true;
        } catch (e) {
            if (request !== reviewSessionRequest) return;
            if (e instanceof DayTurnedError) rollOverIfNewDay();
            else toastStore.show(getErrorMessage(e), 'error');
        } finally {
            reviewSessionOpening = false;
        }
    }
    /** At midnight an open walkthrough takes the new day's list, or closes rather than keep yesterday's. */
    async function refreshReviewSession(): Promise<void> {
        const request = ++reviewSessionRequest;
        try {
            const reading = await readReviewSession();
            if (request !== reviewSessionRequest || !reviewSessionOpen) return;
            reviewSessionReading = reading;
            reviewSessionKey += 1;
        } catch {
            if (request === reviewSessionRequest) reviewSessionOpen = false;
        }
    }

    // The range check over the desk's window (the Species page's day window, or Today), flagged the
    // same way, so the desk never says nothing is waiting while a species check is.
    const UNREAD_RANGE_CHECK: RangeCheckReading = { status: 'loading', checks: [], nearbyRadiusKm: null };
    let rangeCheck = $state.raw<RangeCheckReading>(UNREAD_RANGE_CHECK);
    const speciesChecksLoader = createObservationProjectionLoader({
        fetch: (signal) => readDeskDay(async (window) => {
            const span = window.kind === 'today' ? 'today' : 'day';
            // BirdNET silence only means "not heard" when its rollup for the same window loaded.
            const heard = birdnetEnabled
                ? fetchAudioSpeciesLeaderboard(span, signal).then((response) => response, (error: unknown) => {
                    if (signal.aborted) throw error;
                    return null;
                })
                : Promise.resolve(null);
            const [leaderboard, audio] = await Promise.all([fetchLeaderboardSpecies(span, signal), heard]);
            return { leaderboard, audio };
        }, ({ leaderboard, audio }) => [leaderboard.window_start, audio?.window_start ?? null]),
        apply: ({ value: { leaderboard, audio } }) => {
            const next = readRangeCheck(rangeCheck, leaderboard, audio?.species ?? null);
            if (next.status !== 'unavailable') domesticOffers.measured();
            rangeCheck = next;
            dayReadFailed.checks = next.status === 'unavailable';
        },
        clear: () => { rangeCheck = UNREAD_RANGE_CHECK; domesticOffers.measured(); },
        fail: (e) => {
            if (e instanceof DayTurnedError) { rollOverIfNewDay(); return; }
            rangeCheck = { ...rangeCheck, status: 'unavailable' };
            dayReadFailed.checks = true;
            logger.warn('Species checks unavailable for the dashboard', { message: getErrorMessage(e) });
        },
        settled: () => reportDayRead()
    });
    // The day's safety read and an announced call both read the checks; when both run together
    // (after a reconnect, say) they share one read instead of the second cancelling the first.
    const readSpeciesChecksOnce = createSingleFlightRunner(() => speciesChecksLoader.load());
    /** A person's retry shows it is checking again; a background poll leaves the stated failure in place. */
    function loadSpeciesChecks({ retry = false }: { retry?: boolean } = {}): void {
        if (!canReview) return;
        if (retry && rangeCheck.status === 'unavailable') rangeCheck = { ...rangeCheck, status: 'loading' };
        void speciesChecksLoader.load();
    }
    $effect(() => {
        void birdnetEnabled;
        if (!canReview) { speciesChecksLoader.invalidate(); return; }
        untrack(loadSpeciesChecks);
        return () => speciesChecksLoader.dispose();
    });

    // A flagged species can be a domestic bird the owner keeps under its wild name, as on the Species page.
    const gardenOwner = $derived(canReview && settingsStore.settings?.beta_garden_animals === true);
    const domesticOffers = new DomesticBirdOffers(() => gardenOwner);
    let namedChecks = $derived(rangeCheck.checks.map((check) => ({
        displayName: $birdNames(check, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary).primary,
        scientificName: check.scientific_name ?? null
    })));
    let checksView = $derived<SpeciesChecksView>({
        status: rangeCheck.status,
        names: namedChecks.map((check) => check.displayName),
        nearbyRadiusKm: rangeCheck.nearbyRadiusKm,
        keptBirds: gardenOwner ? domesticOffers.offersFor(namedChecks) : []
    });

    function speciesKept(bird: DomesticBirdKey): void {
        domesticOffers.kept(bird);
        loadSpeciesChecks();
        handleBirdsChanged();
    }

    $effect(() => {
        if (!recordingClipFetchEnabled) return;
        for (const visit of visits) {
            void fullVisitStore.ensureAvailability(visit.best.frigate_event);
        }
    });

    // Visits, as the log counts them. The summary counts the whole window; until it arrives the
    // loaded visits stand in, never the frame count, which is a different unit.
    let windowVisitCount = $derived(summary?.visit_count ?? allVisits.length);
    let windowSpeciesCount = $derived(summary?.top_species.length ?? 0);
    let audioConfirmations = $derived(summary?.audio_confirmations ?? 0);
    // Configuration decides which figures the day bar holds, so loading fills cells rather than adding them.
    let daySlots = $derived(dayBarSlots({
        audioConfigured: birdnetEnabled,
        countingConfigured: publicSettingsStore.settings?.bird_counting_enabled ?? null,
        countedCaptures: summary?.counted_captures ?? null
    }));

    // An owner's Garden switch is in their settings. The day waits for them on a cold load, so the log
    // is read once with the right contents instead of once without Garden and again when they arrive.
    let awaitingSettings = false;
    async function settleGardenSwitch(signal: AbortSignal): Promise<void> {
        if (!authStore.hasOwnerAccess || settingsStore.settings !== null) return;
        awaitingSettings = true;
        try {
            await settingsStore.read();
        } catch {
            // Without settings the log reads birds only; it is read again if the switch arrives on.
        } finally {
            awaitingSettings = false;
        }
        if (signal.aborted) throw new DOMException('The read was aborted.', 'AbortError');
    }

    const summaryLoader = createObservationProjectionLoader({
        fetch: async (signal) => {
            await settleGardenSwitch(signal);
            readGardenAvailable = gardenAvailable;
            // One pair of instants for this load: the summary's window, the visits and Garden all read it.
            const readLog = (window: { startTime: string; endTime: string }) => {
                // A Garden failure is stated beside the birds rather than taking the whole log down.
                const gardenRead = gardenAvailable
                    ? fetchGardenVisits({ start: window.startTime, end: window.endTime, order: 'newest', limit: VISIT_ROW_LIMIT }, signal)
                        .then((page) => ({ page }), (error: unknown) => {
                            if (signal.aborted) throw error;
                            logger.warn('Garden visits unavailable for the field log', { message: getErrorMessage(error) });
                            return { page: null };
                        })
                    : Promise.resolve(null);
                return Promise.all([fetchVisits({ ...window, limit: VISIT_ROW_LIMIT, signal, requestKey: 'dashboard:visits' }), gardenRead]);
            };
            const utcDay = (): string => new Date().toISOString().slice(0, 10);
            const { value, window: desk } = await readDeskDay(async (desk) => {
                const sharedDayAtStart = utcDay();
                let window = { startTime: desk.start.toISOString(), endTime: desk.end.toISOString() };
                let [summaryRes, [visitsRes, gardenRes]] = await Promise.all([fetchDailySummary(desk.kind, signal), readLog(window)]);
                // A guest's shared history can start after the window asked for. The log is read again
                // over the start the figures counted from, so its rows and the figures agree.
                const sharedFrom = authStore.isGuest ? narrowedToSharedDay(desk, summaryRes.window_start) : null;
                if (sharedFrom) {
                    window = { startTime: sharedFrom, endTime: window.endTime };
                    [visitsRes, gardenRes] = await readLog(window);
                }
                // The shared history moves at UTC midnight: a guest read that crossed it is read again.
                const sharedDayMoved = authStore.isGuest && utcDay() !== sharedDayAtStart;
                return { summaryRes, visitsRes, gardenRes, window, sharedDayMoved };
            }, ({ summaryRes }) => [summaryRes.window_start], ({ sharedDayMoved }) => !sharedDayMoved);
            return { ...value, desk };
        },
        apply: ({ summaryRes, visitsRes, gardenRes, window, desk }) => {
            // The chart ends in the hour the server's count did, not the hour the read was sent in.
            const counted = new Date(summaryRes.window_end);
            summary = summaryRes; summaryHour = Number.isNaN(counted.getTime()) ? desk.end.getHours() : counted.getHours(); shownWindow = desk;
            summaryRefreshFailed = false;
            dayReadFailed.summary = false;
            serverVisits = visitsRes.visits.map((visit) => fromServerVisit(visit, window)); totalVisits = visitsRes.total;
            gardenWindow = { start: window.startTime, end: window.endTime };
            gardenUnavailable = gardenRes !== null && gardenRes.page === null;
            // Garden that could not be read shows none of its earlier rows beside "only birds are shown".
            if (gardenRes?.page) { gardenVisits = gardenRes.page.visits; gardenTotal = gardenRes.page.total; }
            else { gardenVisits = []; gardenTotal = 0; }
        },
        clear: () => { summary = null; shownWindow = null; serverVisits = []; totalVisits = 0; gardenVisits = []; gardenTotal = 0; gardenUnavailable = false; summaryRefreshFailed = false; },
        fail: (e) => {
            if (e instanceof DayTurnedError) { rollOverIfNewDay(); return; }
            dayReadFailed.summary = true;
            summaryRefreshFailed = true;
            // An earlier reading that found nothing is no reading once a refresh fails: an empty
            // window is said only of a read that succeeded. A guest keeps nothing a refresh lost.
            if (authStore.isGuest || (summary?.visit_count === 0 && serverVisits.length === 0 && gardenVisits.length === 0)) {
                summary = null; shownWindow = null;
            }
            if (isTransientRequestError(e)) {
                logger.warn('Dashboard summary fetch failed (transient)', { message: getErrorMessage(e) });
            } else {
                logger.error('Failed to load summary', e);
            }
        },
        settled: () => { summaryLoading = false; reportDayRead(); }
    });

    /** True when the day was read; false when the read failed or a newer one replaced it. */
    async function loadSummary(): Promise<boolean> {
        // A retry after a failed first read is loading again, not still failed.
        if (summary === null) summaryLoading = true;
        return summaryLoader.load();
    }

    // The latest read of the day failed; what is on screen, if anything, is an earlier reading.
    let summaryRefreshFailed = $state(false);

    // Until the day has been read, its figures are unknown rather than zero.
    let summaryPending = $derived(summary === null && summaryLoading);
    let summaryUnavailable = $derived(summary === null && !summaryLoading);
    let queueStatus = $derived<ReadingStatus>(reviewReadingStatus);
    let unresolvedCount = $derived<number | null>(
        typeof summary?.unresolved_count === 'number' ? summary.unresolved_count : null
    );

    // A guest's Today starts where the owner's shared history does when that is after their midnight.
    let sharedFrom = $derived(authStore.isGuest && shownWindow ? sharedHistoryStart(shownWindow, summary?.window_start) : null);
    // "Yet today" is said only of a Today that was read and is empty; a failed read says so instead.
    // With Garden unread, only birds were measured, so the empty log says birds.
    let fieldLogEmpty = $derived.by(() => {
        if (gardenUnavailable) {
            if (sharedFrom) {
                return $_('dashboard.no_bird_visits_shared', {
                    values: { time: formatTime(sharedFrom) },
                    default: 'No bird visits since {time}, when the shared history starts.'
                });
            }
            return deskKind === 'today'
                ? $_('dashboard.no_bird_visits_today', { default: 'No bird visits yet today.' })
                : $_('dashboard.no_bird_visits', { default: 'No bird visits in the last 24 hours.' });
        }
        if (sharedFrom) {
            return $_('dashboard.waiting_first_visitor_shared', {
                values: { time: formatTime(sharedFrom) },
                default: 'No visits since {time}, when the shared history starts. New visits appear here as they arrive.'
            });
        }
        return deskKind === 'today'
            ? $_('dashboard.waiting_first_visitor_today', { default: 'No visits yet today. New visits appear here as they arrive.' })
            : null;
    });
    let fieldLogEarlier = $derived(
        deskKind === 'today'
            ? $_('dashboard.field_log.earlier_today', {
                values: { count: hiddenVisitCount },
                default: '{count, plural, one {# earlier visit today, open in Explorer} other {# earlier visits today, open in Explorer}}'
            })
            : null
    );

    /** This device's choice of window, remembered here, read again from the start. */
    function chooseWindow(next: DeskWindowKind): void {
        if (next === windowChoice) return;
        windowChoice = next;
        saveDeskWindowChoice(() => localStorage, next);
        rereadDesk();
    }

    /**
     * Every reading the desk shows, read again for the chosen window. Each is cleared first and its
     * read in flight is dropped, so a slower answer for the window just left can never land under
     * the new name.
     */
    function rereadDesk(): void {
        readingDay = deskWindowStart('today', new Date());
        summaryLoading = true;
        audioSummaryLoading = true;
        summaryLoader.invalidate();
        audioSummaryLoader.invalidate();
        reviewQueueLoader.invalidate();
        speciesChecksLoader.invalidate();
        reviewSessionRequest += 1;
        void loadSummary();
        if (birdnetEnabled) void audioSummaryLoader.load();
        loadReviewQueue();
        loadSpeciesChecks();
        if (reviewSessionOpen) void refreshReviewSession();
    }

    /** Midnight has passed since the day being read was settled: read the new day, once. */
    function rollOverIfNewDay(): void {
        if (windowChoice !== 'today' || deskWindowStart('today', new Date()) === readingDay) return;
        dayTurn += 1;
        rereadDesk();
    }

    // Today becomes another day at local midnight; the open page reads the new one. A read that
    // notices midnight first rolls over sooner.
    $effect(() => {
        if (windowChoice !== 'today') return;
        void dayTurn;
        const timer = setTimeout(() => untrack(rollOverIfNewDay), msUntilNextLocalMidnight(new Date()) + 1000);
        return () => clearTimeout(timer);
    });

    let needsCall = $derived(needsYourCall({
        canReview,
        queueStatus,
        queueTotal: reviewQueue.total,
        checksStatus: checksView.status,
        checkCount: checksView.names.length
    }));

    const DAY_POLL_MS = REFRESH_CADENCE_MS.dashboardDay;

    // The live stream announces every visit, correction and Garden review, and the effects below read
    // the day again for each, so while it is connected the timer is only a slow safety read. Without
    // it, the day is polled every minute as before.
    let dayAudioReading: LiveReading | undefined;
    // New calls are announced to the owner only; a guest's Heard figures poll within the visitor budget.
    const audioFollowsLiveStream = $derived(authStore.hasOwnerAccess && detectionsStore.connected);

    onMount(() => {
        const stopFollowingHistory = detectionsStore.follow();
        void loadSummary();
        daySafetyReading = startLiveReading({
            read: async () => {
                loadReviewQueue();
                await Promise.all([loadSummary(), canReview ? readSpeciesChecksOnce() : Promise.resolve(true)]);
                return !dayReadFailed.summary && !dayReadFailed.checks && !dayReadFailed.queue;
            },
            live: () => detectionsStore.connected,
            pollMs: () => DAY_POLL_MS,
            quietMs: REFRESH_CADENCE_MS.liveSafetyRead,
            readAtStart: false
        });
        // The day bar and the Heard card share this one reading, kept within a visitor's request budget.
        dayAudioReading = startLiveReading({
            read: async ({ announced }) => {
                // "Needs your call" counts a species as heard from the audio rollup too, so a new call
                // can settle a check: read the checks with it rather than at the next day read.
                const [audioRead] = await Promise.all([
                    birdnetEnabled ? audioSummaryLoader.load() : Promise.resolve(true),
                    announced && canReview ? readSpeciesChecksOnce() : Promise.resolve(true)
                ]);
                return audioRead && !(announced && dayReadFailed.checks);
            },
            live: () => audioFollowsLiveStream,
            pollMs: () => authStore.isGuest
                ? Math.max(DAY_POLL_MS, guestRecentAudioPollDelayMs(authStore.publicAccessRateLimitPerMinute))
                : DAY_POLL_MS,
            quietMs: REFRESH_CADENCE_MS.liveSafetyRead,
            readAtStart: false
        });
        return () => { stopFollowingHistory(); daySafetyReading?.stop(); dayAudioReading?.stop(); summaryLoader.dispose(); audioSummaryLoader.dispose(); reviewQueueLoader.dispose(); };
    });

    $effect(() => {
        void detectionsStore.connected;
        daySafetyReading?.liveChanged();
    });

    $effect(() => {
        void audioFollowsLiveStream;
        dayAudioReading?.liveChanged();
    });

    let handledAudioActivity = audioActivity.version;
    $effect(() => {
        const version = audioActivity.version;
        if (version === handledAudioActivity) return;
        handledAudioActivity = version;
        dayAudioReading?.changed();
    });

    // Turning Garden on or off, or signing in as the owner, changes what the log may hold. A read
    // still waiting for the owner's settings decides with them, so it is not started twice.
    let readGardenAvailable = untrack(() => gardenAvailable);
    $effect(() => {
        const available = gardenAvailable;
        if (available === readGardenAvailable || awaitingSettings) return;
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
        const message = $_('garden.batch_dismissed', { default: '{count, plural, one {# photo dismissed.} other {# photos dismissed.}}', values: { count: ids.length } });
        if (skipped > 0) {
            toastStore.warning(`${message} ${$_('garden.batch_skipped', { default: '{count, plural, one {# photo was unchanged because its review or availability changed.} other {# photos were unchanged because their review or availability changed.}}', values: { count: skipped } })}`);
        } else {
            toastStore.success(message);
        }
    }

    let handledVisitMutation = detectionsStore.mutationVersion;
    $effect(() => {
        const version = detectionsStore.mutationVersion;
        if (version <= handledVisitMutation) return;
        handledVisitMutation = version;
        // An owner's correction can confirm a flagged species, so the range check is read again too.
        const timeout = setTimeout(() => { void loadSummary(); loadSpeciesChecks(); }, 2000);
        // Each read asks Frigate about every listed event, so a busy feeder reads this less often.
        // The owner's own decisions read it straight away.
        const queueTimeout = setTimeout(loadReviewQueue, Math.max(2000, lastReviewQueueRead + REVIEW_QUEUE_MIN_INTERVAL_MS - Date.now()));
        return () => { clearTimeout(timeout); clearTimeout(queueTimeout); };
    });

    // What the microphone heard: the day bar's call count and the Heard card read this one summary.
    let audioSummary = $state.raw<AudioSummaryResponse | null>(null);
    let audioSummaryLoading = $state(true);
    let audioSummaryFailed = $state(false);

    const audioSummaryLoader = createObservationProjectionLoader({
        // The Heard figures count the desk's own instants, so they agree with the day bar's window.
        fetch: (signal) => readDeskDay(
            (desk) => fetchAudioSummary({ start_date: desk.start.toISOString(), end_date: desk.end.toISOString() }, signal),
            (value) => [value.window_start]
        ),
        apply: ({ value }) => { audioSummary = value; audioSummaryFailed = false; },
        clear: () => { audioSummary = null; audioSummaryFailed = false; },
        fail: (e) => {
            if (e instanceof DayTurnedError) { rollOverIfNewDay(); return; }
            audioSummaryFailed = true;
            // As with the day: nothing heard is said only of a read that succeeded.
            if (authStore.isGuest || audioSummary?.total === 0) audioSummary = null;
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
            loadSpeciesChecks({ retry: true });
            await Promise.all([
                detectionsStore.loadInitial(),
                loadSummary()
            ]);
        });
    });

    function handleSpeciesSummaryClick(speciesFilter: string) {
        // Over the last 24 hours Today would hide the visits before midnight, so the species alone
        // filters; Today's list opens on Today.
        const day = deskKind === 'today' ? '&date=today' : '';
        onnavigate?.(`/events?species=${encodeURIComponent(speciesFilter)}${day}`);
    }

    /** A bird correction, exclusion or recount changes the day's total and the log's summaries. */
    function handleBirdsChanged(): void {
        void loadSummary();
        loadReviewQueue();
        void detectionsStore.refreshAfterOwnerEdit();
    }
</script>

<div class="space-y-6">
    <DayBar
        visitCount={summary ? windowVisitCount : null}
        countedBirds={summary ? (summary.counted_birds ?? 0) : null}
        countedCaptures={summary ? (summary.counted_captures ?? 0) : null}
        speciesCount={summary ? windowSpeciesCount : null}
        unresolvedCount={unresolvedCount}
        othersAwaitReview={canReview && ((needsCall.checks !== 'clear' && needsCall.checks !== 'off') || needsCall.visits !== 'clear')}
        audioCalls={audioSummary?.total ?? null}
        audioConfirmations={summary ? audioConfirmations : null}
        slots={daySlots}
        loading={summaryPending}
        audioLoading={audioSummaryLoading}
        feed={liveFeedState(detectionsStore.connected, serviceConnectionsStore.connections)}
        windowKind={deskKind}
        choice={windowChoice}
        onwindowchange={chooseWindow}
        {sharedFrom}
    />

    <ProviderWarning {onnavigate} />

    <!-- Field desk: the day reads as one chronological log beside a rail. Below 1920px the rail is one
         column; from there it splits in two, what needs you and what is happening beside the
         reference, so the log keeps a readable row instead of stretching across a wide screen.
         Needs your call comes first in the page, so on a phone the work is above the log; from 1280px
         it heads the rail (across both of its columns from 1920px). -->
    <section
        data-dashboard-field-desk
        class="grid grid-cols-1 items-start gap-6 xl:grid-cols-[minmax(0,1.55fr)_minmax(18rem,0.75fr)] 3xl:grid-cols-[minmax(0,1.4fr)_minmax(0,2fr)]"
    >
        {#if needsCall.visible}
            <div class="min-w-0 xl:col-start-2 xl:row-start-1" data-dashboard-needs-call>
                <ReviewQueueCard
                    queue={reviewQueue}
                    status={queueStatus}
                    checks={checksView}
                    onretry={retryReviewQueue}
                    onreview={openRecord}
                    onreviewall={() => void openReviewSession()}
                    onopenchecks={() => onnavigate?.(speciesChecksLink(deskKind))}
                    onretrychecks={() => loadSpeciesChecks({ retry: true })}
                    onkept={speciesKept}
                    windowKind={deskKind}
                />
            </div>
        {/if}

        <div class="min-w-0 xl:col-start-1 xl:row-span-2 xl:row-start-1" data-dashboard-field-log-column>
            <FieldLog
                rows={fieldLogRows}
                hiddenCount={hiddenVisitCount}
                emptyMessage={fieldLogEmpty}
                hiddenLabel={fieldLogEarlier}
                placeholderRows={VISIT_ROW_LIMIT}
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
                onplay={(detection) => (video = { frigateEvent: detection.frigate_event, heading: videoHeadingFor(detection, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary, $birdNames), shareToken: null, playIntent: 'user' })}
                onseeall={() => onnavigate?.(gardenVisits.length > 0 ? '/events?visitors=all' : '/events')}
                onseewindow={() => onnavigate?.(fieldLogWindowLink(gardenAvailable, deskKind))}
            />
        </div>

        <!-- Under the log on a tablet or small laptop (768 to 1279px) the rail's two groups stand side by
             side rather than as full-width cards; beside the log from 1280px they stack, and from 1920px
             they split again. -->
        <aside class="grid min-w-0 grid-cols-1 items-start gap-6 md:grid-cols-2 xl:col-start-2 xl:grid-cols-1 3xl:grid-cols-2 {needsCall.visible ? 'xl:row-start-2' : 'xl:row-start-1'}">
            <!-- What is happening now. -->
            <div class="flex min-w-0 flex-col gap-6" data-dashboard-rail-now>
                <DeskContextCards
                    detections={deskDetections}
                    visits={allVisits}
                    cameraVisits={summary?.camera_visits ?? null}
                    loading={summaryPending}
                    unavailable={summaryUnavailable}
                    windowKind={deskKind}
                />

                {#if birdnetEnabled}
                    <RecentAudio
                        onNavigate={onnavigate}
                        summary={audioSummary}
                        summaryLoading={audioSummaryLoading}
                        matchedCalls={summary ? audioConfirmations : null}
                        summaryFailed={audioSummaryFailed}
                        windowKind={deskKind}
                    />
                {/if}
            </div>

            <!-- Reference: the shape of the day, the area around the feeder, who comes most. -->
            <div class="flex min-w-0 flex-col gap-6" data-dashboard-rail-reference>
                {#if summary}
                    <DailyHistogram data={summary.hourly_visits ?? []} currentHour={summaryHour} windowKind={deskKind} />
                {:else if summaryLoading}
                    <div class="h-40 animate-pulse rounded-2xl bg-surface-raised motion-reduce:animate-none"></div>
                {/if}

                <NotableNearby
                    canConfigure={canReview}
                    refreshKey={notableRefreshKey}
                    onconfigure={() => onnavigate?.(settingsPartPath('networks'))}
                    onselectspecies={(species) => (selectedSpecies = species)}
                />

                <div data-dashboard-top-visitors>
                    {#if summary}
                        <TopVisitors
                            species={summary.top_species}
                            onSpeciesClick={handleSpeciesSummaryClick}
                            windowKind={deskKind}
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
    {#key reviewSessionKey}
    {@const fullQueue = buildReviewQueue(reviewSessionReading, {
        reviewThreshold,
        limit: Number.MAX_SAFE_INTEGER,
        knownDetections: detectionsStore.detections,
        localChoices: detectionsStore.patchMap
    })}
    <LazyModal loader={loadReviewQueueModal} onclose={() => (reviewSessionOpen = false)}>
        {#snippet children(ReviewQueueModal)}
            <ReviewQueueModal
                onbirdschanged={handleBirdsChanged}
                queue={fullQueue.items}
                moreWaiting={fullQueue.remaining}
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
    {/key}
{/if}

<RecordDialogs
    bind:record={selectedEvent}
    bind:video
    bind:visit={openedVisit}
    onViewSpecies={(species: string) => (selectedSpecies = species)}
    onbirdschanged={handleBirdsChanged}
/>

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
<style>
    /* From 1280px the log spans the rail's two rows: Needs your call, then the rest of the rail. The
       rail's first row is only as tall as the card, so the log's height never opens a gap under it. */
    @media (min-width: 1280px) {
        [data-dashboard-field-desk] {
            grid-template-rows: auto 1fr;
        }
    }
</style>
