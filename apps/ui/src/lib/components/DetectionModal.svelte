<script lang="ts">
    import { compassPointKey, weatherConditionMessage } from '../utils/weather-condition';
    import { formatSnapshotFallbackReason } from '../utils/snapshot-fallback-reason';
    import DialogHeader from './ui/DialogHeader.svelte';
    import ClassificationSource from './ClassificationSource.svelte';
    import RecordTechnicalDetails from './RecordTechnicalDetails.svelte';
    import RangeFallbackNote from './RangeFallbackNote.svelte';
    import TaxonomyLineage from './TaxonomyLineage.svelte';
    import Map from './Map.svelte';
    import {
        getSnapshotUrl,
        getThumbnailUrl,
        fetchEvents,
        getOriginalFrigateSnapshotUrl,
        fetchSnapshotStatus,
        fetchSnapshotCandidates,
        dismissSnapshotCandidate,
        applySnapshotCandidate,
        generateHighQualityBirdCropSnapshot,
        updateDetectionSpecies,
        hideDetection,
        deleteDetection,
        favoriteDetection,
        fetchArchiveStatus,
        retryArchive,
        type ArchiveStatus,
        unfavoriteDetection,
        searchSpecies,
        fetchFeederSpecies,
        fetchEventAudioContext,
        fetchCommonNameOverride,
        setCommonNameOverride,
        clearCommonNameOverride,
        type SearchResult,
        type SpeciesInfo,
        type AudioContextDetection,
        type SnapshotStatusResponse,
        type SnapshotCandidate,
        type SnapshotDismissalTarget,
        type BirdObservation
    } from '../api';
    import type { Detection } from '../api';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import FrameStrip from './FrameStrip.svelte';
    import { MediaQuery, SvelteSet } from 'svelte/reactivity';
    import CountedBirds from './CountedBirds.svelte';
    import BirdScanControl from './BirdScanControl.svelte';
    import { BirdScan } from '../utils/bird-scan.svelte';
    import { birdScanUnavailableText } from '../utils/bird-scan-standing';
    import MediaImage from './MediaImage.svelte';
    import RecordAiAnalysis from './record/RecordAiAnalysis.svelte';
    import { recordClassificationKey } from './record/record-classification';
    import RecordAudioEvidence from './record/RecordAudioEvidence.svelte';
    import RecordInaturalist from './record/RecordInaturalist.svelte';
    import RecordSpeciesReference from './record/RecordSpeciesReference.svelte';
    import RecordVideoStatusNotice from './record/RecordVideoStatusNotice.svelte';
    import { currentMoment, groupCandidatesIntoMoments, outlineLabelClass, outlineLabelPlace, preferredCandidate, type FrameMoment } from '../utils/frame-moments';
    import { WholeScenePeek } from '../utils/whole-scene-peek.svelte';
    import { photoFitFor, type PhotoFit } from '../utils/photo-fit';
    import { speciesPickerNames } from '../utils/species-picker';
    import { detectionsStore, type ReclassificationProgress } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { classifierLabelsStore } from '../stores/classifier_labels.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { confirmAction } from '../stores/confirm_dialog.svelte';
    import { birdNames } from '../naming';
    import { _ } from 'svelte-i18n';
    import { onDestroy, onMount, untrack } from 'svelte';
    import { trapFocus } from '../utils/focus-trap';
    import { FRIGATE_LOGO_URL } from '../assets';
    import { getErrorMessage } from '../utils/error-handling';
    import {
        getClassificationInputKind,
        getDetectionClassificationSource,
        shouldShowVideoStatusNotice
    } from '../detection-classification-source';
    import { formatDateTime } from '../utils/datetime';
    import { formatTemperature } from '../utils/temperature';
    import { getManualTagSearchOptions } from '../search/manual-tag-search';
    import {
        formatPrecipitation,
        formatWindSpeed,
        getTemperatureUnitForSystem,
        resolveWeatherUnitSystem
    } from '../utils/weather-units';
    import { formatIlluminance } from '../utils/illuminance';
    import { getVideoFailureInsight, hasFrigateMediaIssue } from '../utils/frigate-errors';
    import { frigateEventNotice, frigateEventReading } from '../utils/frigate-event-reading';
    import { isVideoPromotionGated } from '../video-promotion-gate';
    import { applyManualTagResult } from '../utils/manual-tag';
    import { findMatchingFullFrameCandidate, findScanFrameCandidate, sameFrameCropCandidates } from '../utils/detection-evidence';
    import { intersectVisibleViewport } from '../utils/visible-viewport';
    import { SCORE_FILL, scoreBand } from '../utils/score-tone';
    import { archiveFailureView } from '../utils/archive-failure';
    import { moveDetectionToGarden } from '../api/events';
    import { fetchGardenDomesticBirds } from '../api/garden';
    import GardenDomesticSuggestion from './GardenDomesticSuggestion.svelte';
    import { domesticBirdForRecord, domesticBirdName, type DomesticBirdOption } from '../utils/domestic-birds';

    const FRIGATE_MISSING_DOCS_URL = 'https://github.com/Jellman86/YetAnother-WhosAtMyFeeder/blob/dev/docs/troubleshooting/frigate-event-not-found.md';

    interface Props {
        detection: Detection;
        llmReady: boolean;
        showVideoButton?: boolean;
        onClose: () => void;
        onReclassify?: (detection: Detection) => void;
        onPlayVideo?: (frigateEvent: string, playIntent?: 'auto' | 'user') => void;
        onFetchFullVisit?: (detection: Detection) => void;
        onDeleteSuccess?: (frigateEvent: string, detectionTime?: string) => void | Promise<void>;
        onHideSuccess?: (frigateEvent: string, detectionTime: string | undefined, isHidden: boolean) => void | Promise<void>;
        onViewSpecies: (speciesName: string) => void;
        onbirdschanged?: () => void;
        readOnly?: boolean;
        fullVisitAvailable?: boolean;
        fullVisitFetched?: boolean;
        fullVisitFetchState?: 'idle' | 'fetching' | 'ready' | 'partial' | 'failed';
    }

    let {
        detection,
        llmReady,
        showVideoButton = false,
        onClose,
        onReclassify,
        onPlayVideo,
        onFetchFullVisit,
        onDeleteSuccess,
        onHideSuccess,
        onViewSpecies,
        onbirdschanged,
        readOnly = false,
        fullVisitAvailable = false,
        fullVisitFetched = false,
        fullVisitFetchState = 'idle'
    }: Props = $props();
    const publicEventId = $derived(detection.frigate_event);
    $effect(() => {
        const version = detectionsStore.publicHistoryVersion;
        const eventId = publicEventId;
        if (!version || !authStore.isGuest || readOnly) return;
        const controller = new AbortController();
        untrack(() => {
            void fetchEvents({ eventId, limit: 1, fields: 'detail', signal: controller.signal,
                requestKey: 'public-open-detection' }).then(([allowed]) => {
                if (controller.signal.aborted) return;
                if (!allowed) onClose();
                else detection = allowed;
            }).catch(() => {
                if (!controller.signal.aborted) onClose();
            });
        });
        return () => controller.abort();
    });
    let currentClassificationSource = $derived(getDetectionClassificationSource(detection));
    let classificationInputKind = $derived(getClassificationInputKind(detection.video_classification_input_source));
    let classificationInputLabel = $derived.by(() => {
        if (classificationInputKind === 'video_crop') {
            return $_('detection.video_analysis.input_video_crop', { default: 'Cropped video frames' });
        }
        if (classificationInputKind === 'video_full') {
            return $_('detection.video_analysis.input_video_full', { default: 'Full video frames' });
        }
        if (classificationInputKind === 'snapshot_crop') {
            return $_('detection.video_analysis.input_snapshot_crop', { default: 'Cropped snapshot' });
        }
        if (classificationInputKind === 'snapshot_full') {
            return $_('detection.video_analysis.input_snapshot_full', { default: 'Full snapshot' });
        }
        if (classificationInputKind === 'upstream') {
            return $_('detection.video_analysis.input_frigate_sublabel', { default: 'Frigate species label' });
        }
        return null;
    });
    let completedClassificationTitle = $derived.by(() => {
        if (classificationInputKind === 'upstream') {
            return $_('detection.video_analysis.frigate_fallback_title', { default: 'Result from Frigate' });
        }
        if (classificationInputKind === 'snapshot_crop' || classificationInputKind === 'snapshot_full') {
            return $_('detection.video_analysis.fallback_title', { default: 'Result from snapshot' });
        }
        return $_('detection.video_analysis.title');
    });
    let completedClassificationDescription = $derived.by(() => {
        if (classificationInputKind === 'upstream') {
            return $_('detection.video_analysis.frigate_fallback_desc', { default: "Local image analysis did not clear policy, so YA-WAMF retained Frigate's trusted species label." });
        }
        if (classificationInputKind === 'snapshot_crop' || classificationInputKind === 'snapshot_full') {
            return $_('detection.video_analysis.fallback_desc', { default: 'Video analysis was not available, so this capture was named from a single frame. The score may be lower.' });
        }
        return $_('detection.video_analysis.verified_desc');
    });
    let hideActionLabel = $derived(
        detection.is_hidden
            ? $_('actions.unhide_detection', { default: 'Unhide record' })
            : $_('actions.hide_detection')
    );

    // True when video classification completed with a real species but did not
    // match any current primary identity field, so owner confirmation is needed.
    let videoPromotionGated = $derived(isVideoPromotionGated(detection));
    const isManualObservation = $derived(detection.observation_source === 'manual_upload');
    // An uploaded video is kept with the observation and serves photo choices and
    // Score again like any visit's clip; an uploaded photo has neither.
    const hasFrameSource = $derived(!isManualObservation || Boolean(detection.has_clip));

    // State
    let modalElement = $state<HTMLElement | null>(null);
    let manualTagViewportStyle = $state<string | undefined>(undefined);
    let viewportAnimationFrame: number | undefined;
    let previousBodyPosition = '';
    let previousBodyTop = '';
    let previousBodyWidth = '';
    let previousBodyOverflow = '';
    let previousHtmlOverflow = '';
    let scrollLockY = 0;
    let scrollLocked = false;
    let audioContextLoading = $state(false);
    let audioContextLoaded = $state(false);
    let audioContext = $state<AudioContextDetection[]>([]);
    let audioContextSuppressed = $state(0);
    let audioContextError = $state<string | null>(null);
    // Enrichment state
    let failedSpeciesReferenceUrl = $state<string | null>(null);
    let commonNameEditorOpen = $state(false);
    let moreActionsOpen = $state(false);
    let speciesInfo = $state.raw<SpeciesInfo | null>(null);
    let commonNameOverride = $state<string | null>(null);
    let commonNameOverrideInput = $state('');
    let commonNameOverrideSaving = $state(false);
    let commonNameOverrideLoadedFor = $state<string | null>(null);

    $effect(() => {
        if (modalElement) {
            return trapFocus(modalElement);
        }
    });

    function lockDocumentScroll() {
        if (scrollLocked || typeof document === 'undefined' || typeof window === 'undefined') return;
        const body = document.body;
        const html = document.documentElement;
        scrollLockY = window.scrollY;
        previousBodyPosition = body.style.position;
        previousBodyTop = body.style.top;
        previousBodyWidth = body.style.width;
        previousBodyOverflow = body.style.overflow;
        previousHtmlOverflow = html.style.overflow;
        body.style.position = 'fixed';
        body.style.top = `-${scrollLockY}px`;
        body.style.width = '100%';
        body.style.overflow = 'hidden';
        html.style.overflow = 'hidden';
        scrollLocked = true;
    }

    function unlockDocumentScroll() {
        if (!scrollLocked || typeof document === 'undefined' || typeof window === 'undefined') return;
        const body = document.body;
        const html = document.documentElement;
        body.style.position = previousBodyPosition;
        body.style.top = previousBodyTop;
        body.style.width = previousBodyWidth;
        body.style.overflow = previousBodyOverflow;
        html.style.overflow = previousHtmlOverflow;
        window.scrollTo(0, scrollLockY);
        scrollLocked = false;
    }

    function syncManualTagViewport(): void {
        if (typeof window === 'undefined' || !modalElement || !window.visualViewport) {
            manualTagViewportStyle = undefined;
            return;
        }

        const modalBounds = modalElement.getBoundingClientRect();
        const visibleBounds = intersectVisibleViewport(
            { top: modalBounds.top, height: modalBounds.height },
            {
                offsetTop: window.visualViewport.offsetTop,
                height: window.visualViewport.height
            }
        );
        const isClipped = visibleBounds.top > 0.5 || visibleBounds.height < modalBounds.height - 0.5;

        manualTagViewportStyle = isClipped && visibleBounds.height > 0
            ? `top:${Math.round(visibleBounds.top)}px;height:${Math.round(visibleBounds.height)}px;`
            : undefined;
    }

    function scheduleManualTagViewportSync(): void {
        if (typeof window === 'undefined' || viewportAnimationFrame !== undefined) return;
        viewportAnimationFrame = window.requestAnimationFrame(() => {
            viewportAnimationFrame = undefined;
            syncManualTagViewport();
        });
    }

    function withCacheBust(url: string, token: string): string {
        const separator = url.includes('?') ? '&' : '?';
        return `${url}${separator}v=${token}`;
    }

    let snapshotControlsEpoch = 0;
    let snapshotControlsSubject: string | null = null;

    async function refreshSnapshotControls(eventId: string) {
        const requestEpoch = ++snapshotControlsEpoch;
        const listRevision = candidateListRevision;
        const parentIdentity = untrack(() => countedParentIdentity);
        const isCurrent = () => requestEpoch === snapshotControlsEpoch
            && detection?.frigate_event === eventId && hasOwnerDetectionActions;
        // A photo choice changed while this read was out: its answer may predate that change.
        const listIsFresh = () => listRevision === candidateListRevision;
        if (!isCurrent()) return;
        snapshotCandidatesLoading = true;
        snapshotCandidatesError = false;
        try {
            const [status, candidateList] = await Promise.all([
                fetchSnapshotStatus(eventId),
                fetchSnapshotCandidates(eventId)
            ]);
            if (!isCurrent()) return;
            if (listIsFresh()) {
                snapshotCandidates = candidateList.candidates ?? [];
                asRecordedDismissed = Boolean(candidateList.as_recorded_dismissed);
                snapshotStatus = status;
                currentSnapshotCandidateId = candidateList.current_candidate_id ?? null;
                currentSnapshotSource = candidateList.current_source ?? status.source ?? null;
            }
            if (parentIdentity === countedParentIdentity) {
                countedBirds = candidateList.birds ?? [];
                countedBirdsGeneration += 1;
                countedBirdsError = false;
                countedBirdsLoading = false;
            }
        } catch {
            if (!isCurrent()) return;
            if (listIsFresh()) {
                snapshotStatus = null;
                snapshotCandidates = [];
                asRecordedDismissed = false;
                snapshotCandidatesError = true;
                currentSnapshotCandidateId = null;
                currentSnapshotSource = null;
            }
            if (parentIdentity === countedParentIdentity) {
                countedBirds = [];
                countedBirdsGeneration += 1;
                countedBirdsLoading = false;
            }
        } finally {
            if (isCurrent()) {
                snapshotCandidatesLoading = false;
            }
        }
    }

    const syncDarkMode = () => {
        if (typeof document === 'undefined') return;
        isDarkMode = document.documentElement.classList.contains('dark');
    };

    onMount(() => {
        syncDarkMode();
        if (typeof document === 'undefined') return;
        const observer = new MutationObserver(syncDarkMode);
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
        return () => {
            observer.disconnect();
        };
    });

    onMount(() => {
        lockDocumentScroll();
        return () => {
            unlockDocumentScroll();
        };
    });

    onMount(() => {
        if (typeof window === 'undefined') return;
        const visualViewport = window.visualViewport;
        const modalResizeObserver = typeof ResizeObserver === 'undefined'
            ? undefined
            : new ResizeObserver(scheduleManualTagViewportSync);

        syncManualTagViewport();
        if (modalElement) {
            modalResizeObserver?.observe(modalElement);
        }
        window.addEventListener('resize', scheduleManualTagViewportSync);
        visualViewport?.addEventListener('resize', scheduleManualTagViewportSync);
        visualViewport?.addEventListener('scroll', scheduleManualTagViewportSync);

        return () => {
            modalResizeObserver?.disconnect();
            window.removeEventListener('resize', scheduleManualTagViewportSync);
            visualViewport?.removeEventListener('resize', scheduleManualTagViewportSync);
            visualViewport?.removeEventListener('scroll', scheduleManualTagViewportSync);
            if (viewportAnimationFrame !== undefined) {
                window.cancelAnimationFrame(viewportAnimationFrame);
                viewportAnimationFrame = undefined;
            }
        };
    });

    $effect(() => {
        const eventId = detection?.frigate_event;
        // A changed authoritative count also retires an open record's older scan.
        void detection?.bird_summary;
        // detection_updated precedes the run's photo work; only the settled run has saved it.
        void settledMediaVersion;
        snapshotControlsEpoch += 1;
        if (!eventId || !hasOwnerDetectionActions) {
            snapshotControlsSubject = null;
            snapshotStatus = null;
            snapshotCandidates = [];
            asRecordedDismissed = false;
            countedBirds = [];
            snapshotCandidatesLoading = false;
            currentSnapshotCandidateId = null;
            currentSnapshotSource = null;
            return;
        }

        if (snapshotControlsSubject !== eventId) {
            snapshotControlsSubject = eventId;
            undoablePhotoRemoval = null;
            snapshotCandidates = [];
            asRecordedDismissed = false;
            countedBirds = [];
            // Keep keyed rows and focus while rereading this same capture.
            untrack(() => { countedBirdsGeneration += 1; });
        }
        snapshotCandidatesError = false;
        snapshotCandidatesLoading = true;

        void (async () => {
            try {
                await refreshSnapshotControls(eventId);
            } catch {
                // refreshSnapshotControls already set conservative state
            }
        })();
        return () => { snapshotControlsEpoch += 1; };
    });

    let showTagDropdown = $state(false);
    let updatingTag = $state(false);
    let pendingManualTagId = $state<string | null>(null);
    let favoritePending = $state(false);
    // The favourite's archive (#178). Pending is polled briefly so the star can say when the
    // photograph and clip are actually kept; the worker does not broadcast its progress.
    let archiveStatus = $state<ArchiveStatus | null>(null);
    // Whether that status was read for this record: until it is, a failed copy claims no loss.
    let archiveRead = $state<'reading' | 'read' | 'failed'>('reading');
    // Bumped by "Check again" to read the status once more after a failed read.
    let archiveCheckAttempt = $state(0);
    let archiveRetrying = $state(false);
    const ARCHIVE_POLL_MS = 4000;
    const ARCHIVE_POLL_LIMIT = 45;
    $effect(() => {
        const eventId = detection?.frigate_event;
        const wanted = !!detection?.is_favorite && authStore.hasOwnerAccess && !readOnly;
        // Read so that a retry (which sets the record back to pending) restarts the poll.
        void detection?.archive_state;
        void archiveCheckAttempt;
        if (!eventId || !wanted) {
            archiveStatus = null;
            return;
        }
        // Untracked: this effect writes the status, and must not re-run because it did.
        if (untrack(() => archiveStatus?.event_id) !== eventId) archiveRead = 'reading';
        let cancelled = false;
        let polls = 0;
        let timer: ReturnType<typeof setTimeout> | null = null;
        const load = async () => {
            try {
                const status = await fetchArchiveStatus(eventId);
                if (cancelled) return;
                archiveStatus = status;
                archiveRead = 'read';
                const state = asArchiveState(status.state);
                if (state && state !== detection.archive_state) {
                    detection.archive_state = state;
                    detectionsStore.updateDetection({ ...detection, archive_state: state });
                }
                if (status.state === 'pending' && polls < ARCHIVE_POLL_LIMIT) {
                    polls += 1;
                    timer = setTimeout(load, ARCHIVE_POLL_MS);
                }
            } catch {
                // The star still works without the detail; the state on the record stands, and a
                // failed copy says that what it kept could not be checked.
                if (!cancelled && archiveStatus?.event_id !== eventId) archiveRead = 'failed';
            }
        };
        void load();
        return () => {
            cancelled = true;
            if (timer) clearTimeout(timer);
        };
    });
    const ARCHIVE_STATE_VALUES = new Set(['pending', 'durable', 'unavailable', 'failed']);
    function asArchiveState(value: string | null | undefined): Detection['archive_state'] {
        return value && ARCHIVE_STATE_VALUES.has(value) ? (value as Detection['archive_state']) : null;
    }
    function formatArchiveSize(bytes: number): string {
        if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
        if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
        return `${bytes} B`;
    }
    const archiveState = $derived(
        (archiveStatus && archiveStatus.event_id === detection?.frigate_event ? archiveStatus.state : null) ?? detection?.archive_state ?? null
    );
    const archiveLabel = $derived.by(() => {
        switch (archiveState) {
            case 'durable':
                return archiveStatusHere?.clip_state === 'unavailable'
                    ? $_('detection.archive_photo_only', { default: 'Photo archived, no clip to keep' })
                    : $_('detection.archive_durable', {
                          values: { size: formatArchiveSize(archiveStatusHere?.bytes ?? 0) },
                          default: 'Archived, {size}'
                      });
            case 'unavailable':
                return $_('detection.archive_unavailable', { default: 'Nothing left to archive' });
            case 'failed':
                return $_('detection.archive_failed', { default: 'Archive failed' });
            case 'pending':
                return $_('detection.archive_pending', { default: 'Archiving photo and clip' });
            default:
                return '';
        }
    });
    // A failed copy says what was not kept, why and what to do, not just "Archive failed".
    // The status is used only when it was read for this record, never one left from another.
    const archiveStatusHere = $derived(archiveStatus && archiveStatus.event_id === detection?.frigate_event ? archiveStatus : null);
    const archiveFailure = $derived.by(() => {
        if (archiveState !== 'failed') return null;
        const view = archiveFailureView(archiveStatusHere, archiveRead);
        if (view.kind === 'checking') {
            return { kind: view.kind, lost: $_('detection.archive_checking', { default: "Checking what this favourite's own copy kept…" }) };
        }
        if (view.kind === 'unchecked') {
            return { kind: view.kind, lost: $_('detection.archive_unchecked', { default: "This favourite's own copy reported a problem, but what it kept could not be checked." }) };
        }
        const explained = view.explanation;
        const lost = {
            both: $_('detection.archive_failed_both', { default: "This favourite's own copy of its photo and clip could not be saved." }),
            photo: $_('detection.archive_failed_photo', { default: "This favourite's own copy of its photo could not be saved." }),
            clip: $_('detection.archive_failed_clip', { default: "This favourite's own copy of its clip could not be saved." })
        }[explained.lost];
        const cause = {
            frigate_unreachable: $_('detection.archive_cause.frigate_unreachable', { default: 'Frigate could not be reached. Check that Frigate is running and its address in Settings → Connection.' }),
            frigate_timeout: $_('detection.archive_cause.frigate_timeout', { default: 'Frigate did not answer in time. Check that Frigate is running and not overloaded.' }),
            frigate_refused: $_('detection.archive_cause.frigate_refused', { default: "Frigate refused YA-WAMF's request. Check the Frigate access settings in Settings → Connection." }),
            frigate_error: $_('detection.archive_cause.frigate_error', { default: 'Frigate answered with an error of its own. Check its logs.' }),
            clip_cut_short: $_('detection.archive_cause.clip_cut_short', { default: 'The clip download was cut short.' }),
            disk_full: $_('detection.archive_cause.disk_full', { default: 'The disk that holds the data folder is full. Free some space.' }),
            disk_error: $_('detection.archive_cause.disk_error', { default: 'The data folder could not be written to. Check that it exists and YA-WAMF may write to it.' }),
            unknown: $_('detection.archive_cause.unknown', { default: 'The cause was not recorded.' })
        }[explained.cause];
        const retry = explained.retryDue
            ? $_('detection.archive_retry_due', { default: 'YA-WAMF tries again by itself shortly. The visit stays in your history either way.' })
            : explained.retryAt !== null
            ? $_('detection.archive_retry_scheduled', { values: { at: formatDateTime(explained.retryAt) }, default: 'YA-WAMF tries again by itself at {at}. The visit stays in your history either way.' })
            : $_('detection.archive_retry_spent', { default: 'YA-WAMF has stopped trying by itself. The visit stays in your history either way.' });
        return { kind: view.kind, lost, cause, retry };
    });

    async function handleArchiveRetry() {
        if (!detection || archiveRetrying) return;
        archiveRetrying = true;
        try {
            archiveStatus = await retryArchive(detection.frigate_event);
            detection.archive_state = asArchiveState(archiveStatus.state) ?? 'pending';
            detectionsStore.updateDetection({ ...detection, archive_state: detection.archive_state });
        } catch (e) {
            toastStore.error(getErrorMessage(e) || $_('common.error', { default: 'Action failed' }));
        } finally {
            archiveRetrying = false;
        }
    }
    let snapshotStatus = $state<SnapshotStatusResponse | null>(null);
    let snapshotCandidates = $state<SnapshotCandidate[]>([]);
    let asRecordedDismissed = $state(false);
    /**
     * Advanced by each answered photo-choice change. A candidate read sent before it may describe
     * the list before the change, so it is not allowed to replace the change's own answer.
     */
    let candidateListRevision = 0;
    /** The capture whose last removed photo choice can still be undone, so its strip stays to offer Undo. */
    let undoablePhotoRemoval = $state<string | null>(null);
    let countedBirds = $state<BirdObservation[]>([]);
    /** Advanced on every reread of the birds, so an edit answered after it is not applied. */
    let countedBirdsGeneration = $state(0);
    let countedBirdsLoading = $state(false);
    let countedBirdsError = $state(false);
    const countedParentIdentity = $derived(JSON.stringify([
        detection.category_name, detection.scientific_name, detection.common_name,
        detection.display_name, detection.score, detection.manual_tagged
    ]));
    let countedIdentitySubject: { eventId: string; identity: string } | null = null;

    $effect(() => {
        const eventId = detection.frigate_event;
        const identity = countedParentIdentity;
        const previous = countedIdentitySubject;
        countedIdentitySubject = hasOwnerDetectionActions ? { eventId, identity } : null;
        // The media read owns a new capture. Parent changes reread only bird names:
        // detection_updated can arrive before the run has finished saving its photos.
        if (!hasOwnerDetectionActions || previous?.eventId !== eventId) {
            countedBirdsLoading = false;
            countedBirdsError = false;
            return;
        }
        if (previous.identity === identity) return;
        const mediaEpoch = snapshotControlsEpoch;
        let cancelled = false;
        const isCurrent = () => !cancelled && snapshotControlsEpoch === mediaEpoch
            && detection.frigate_event === eventId && countedParentIdentity === identity && hasOwnerDetectionActions;
        countedBirdsLoading = true;
        countedBirdsError = false;
        untrack(() => { countedBirdsGeneration += 1; });
        void (async () => {
            try {
                const response = await fetchSnapshotCandidates(eventId);
                if (!isCurrent()) return;
                countedBirds = response.birds ?? [];
                countedBirdsGeneration += 1;
            } catch {
                if (isCurrent()) countedBirdsError = true;
            } finally {
                if (isCurrent()) countedBirdsLoading = false;
            }
        })();
        return () => { cancelled = true; };
    });
    let snapshotCandidatesLoading = $state(false);
    let snapshotCandidatesError = $state(false);
    // Photo work belongs to the capture that asked for it: another record neither shows it as its
    // own nor waits for it, and a request that finishes after a switch still clears its own mark.
    const photoApplyEvents = new SvelteSet<string>();
    const photoGenerateEvents = new SvelteSet<string>();
    const snapshotApplyPending = $derived(photoApplyEvents.has(detection.frigate_event));
    const snapshotGeneratePending = $derived(photoGenerateEvents.has(detection.frigate_event));
    let currentSnapshotCandidateId = $state<string | null>(null);
    let currentSnapshotSource = $state<string | null>(null);
    /** The strip moment being saved as the photograph, while the request is in flight. */
    let applyingMoment = $state<{ eventId: string; key: string } | null>(null);
    const applyingMomentKey = $derived(applyingMoment?.eventId === detection.frigate_event ? applyingMoment.key : null);
    let snapshotRefreshToken = $state(Date.now());
    const settledMediaVersion = $derived(
        detectionsStore.settledMediaVersion(detection.frigate_event)
    );
    const snapshotCacheToken = $derived(`${snapshotRefreshToken}.${settledMediaVersion}`);
    let tagSearchQuery = $state('');
    let searchResults = $state<SearchResult[]>([]);
    let isSearching = $state(false);
    const debugUiEnabled = $derived(settingsStore.settings?.debug_ui_enabled ?? false);
    let isDarkMode = $state(false);

    

    // Reclassification progress
    let reclassifyProgress = $derived(
        detectionsStore.progressMap.get(detection.frigate_event) || null
    );
    let canPlayVideo = $derived(showVideoButton && !!onPlayVideo && (detection.has_clip || fullVisitFetched) && !reclassifyProgress);
    let showFetchFullVisitAction = $derived(!!onFetchFullVisit && fullVisitAvailable && !fullVisitFetched && (fullVisitFetchState === 'partial' || fullVisitFetchState === 'failed') && !reclassifyProgress);
    let fullVisitFetchLabel = $derived.by(() => {
        if (fullVisitFetchState === 'fetching') {
            return $_('video_player.fetching_full_visit', { default: 'Fetching...' });
        }
        if (fullVisitFetchState === 'partial' || fullVisitFetchState === 'failed') {
            return $_('video_player.fetch_full_visit_retry', { default: 'Retry full clip' });
        }
        return $_('video_player.fetch_full_visit', { default: 'Fetch full clip' });
    });
    let awaitingReclassifyOverlay = $state(false);
    let videoAnalysisStatus = $derived(detection.video_classification_status ?? null);
    let videoAnalysisActive = $derived(videoAnalysisStatus === 'processing' || videoAnalysisStatus === 'pending');

    // Naming logic
    const showCommon = $derived(settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true);
    const preferSci = $derived(settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false);
    const namingDetection = $derived({
        ...detection,
        common_name: commonNameOverride ?? detection.common_name
    });
    const naming = $derived($birdNames(namingDetection, showCommon, preferSci));
    const primaryName = $derived(naming.primary);
    const subName = $derived(naming.secondary);
    const lateAudioMatch = $derived.by(() => {
        const matches = audioContext.filter((audio) => audio.matches_visual);
        if (!matches.length) return null;
        return [...matches].sort(
            (a, b) => b.confidence - a.confidence || Math.abs(a.offset_seconds) - Math.abs(b.offset_seconds)
        )[0];
    });
    const effectiveAudioConfirmed = $derived(Boolean(detection.audio_confirmed || lateAudioMatch));
    const effectiveAudioSpecies = $derived(
        detection.audio_confirmed ? detection.audio_species : (lateAudioMatch?.species ?? detection.audio_species)
    );
    const effectiveAudioScore = $derived(
        detection.audio_confirmed ? detection.audio_score : (lateAudioMatch?.confidence ?? detection.audio_score)
    );
    const audioContextSpecies = $derived.by(() => {
        const seen = new Set<string>();
        const values: string[] = [];
        const add = (candidate: unknown) => {
            if (typeof candidate !== 'string') return;
            const normalized = candidate.trim();
            if (!normalized) return;
            const key = normalized.toLowerCase();
            if (seen.has(key)) return;
            seen.add(key);
            values.push(normalized);
        };
        add(effectiveAudioSpecies);
        for (const species of detection.audio_context_species ?? []) {
            add(species);
        }
        for (const audio of audioContext) {
            add(audio.species);
        }
        return values;
    });
    const hasAudioContext = $derived(!isManualObservation && (effectiveAudioConfirmed || audioContextSpecies.length > 0));
    const audioNearbySummary = $derived(audioContextSpecies.join(', '));
    const audioFactValue = $derived.by(() => {
        if (effectiveAudioConfirmed) {
            // The one place the matching call is stated; the audio section below shows its evidence.
            const species = effectiveAudioSpecies ?? $_('detection.fact_heard_yes', { default: 'matching call' });
            return effectiveAudioScore ? `${species} · ${Math.round(effectiveAudioScore * 100)}%` : species;
        }
        if (audioContextLoading) return $_('common.loading');
        if (audioContextError || !audioContextLoaded) return $_('common.unavailable');
        return $_('detection.fact_heard_no', { default: 'no matching call' });
    });

    // Pick the best audioContext entry to render its BirdNET-Go spectrogram
    // alongside the audio match card. When the visual detection was audio-
    // confirmed, prefer the entry whose species matches detection.audio_species.
    // Otherwise fall back to whichever context entry is closest in time.
    const matchedAudioEntry = $derived.by(() => {
        if (!audioContext.length) return null;
        if (lateAudioMatch?.birdnet_id != null) return lateAudioMatch;
        const target = (effectiveAudioSpecies || '').trim().toLowerCase();
        if (target) {
            const match = audioContext.find(
                (a) => (a.species || '').trim().toLowerCase() === target && a.birdnet_id != null
            );
            if (match) return match;
        }
        const withId = audioContext.filter((a) => a.birdnet_id != null);
        if (!withId.length) return null;
        return [...withId].sort(
            (a, b) => Math.abs(a.offset_seconds) - Math.abs(b.offset_seconds)
        )[0];
    });
    // Resolve persisted context for every visual event. BirdNET-Go can publish
    // after the visual ingest path has completed, so stored audio fields are not
    // a reliable indication that nearby audio exists.
    $effect(() => {
        const eventId = detection.frigate_event;
        if (detection.observation_source === 'manual_upload') {
            untrack(() => {
                audioContext = [];
                audioContextSuppressed = 0;
                audioContextLoaded = true;
                audioContextLoading = false;
                audioContextError = null;
            });
            return;
        }
        const controller = new AbortController();
        untrack(() => {
            audioContext = [];
            audioContextSuppressed = 0;
            audioContextLoaded = false;
            audioContextLoading = true;
            audioContextError = null;
        });
        void (async () => {
            try {
                const context = await fetchEventAudioContext(eventId, controller.signal);
                if (controller.signal.aborted || detection.frigate_event !== eventId) return;
                audioContext = context.detections;
                audioContextSuppressed = context.suppressed_by_mapping ?? 0;
                audioContextLoaded = true;
            } catch (error) {
                if (controller.signal.aborted || (error instanceof Error && error.name === 'AbortError')) return;
                if (detection.frigate_event !== eventId) return;
                audioContextError = $_('common.error');
            } finally {
                if (!controller.signal.aborted && detection.frigate_event === eventId) {
                    audioContextLoading = false;
                }
            }
        })();

        return () => controller.abort();
    });
    const inatEnabled = $derived(settingsStore.settings?.inaturalist_enabled ?? authStore.inaturalistEnabled ?? false);
    const inatConnectedUser = $derived(settingsStore.settings?.inaturalist_connected_user ?? null);
    const canShowInat = $derived(!readOnly && authStore.canModify && inatEnabled && !!inatConnectedUser);
    const hasOwnerDetectionActions = $derived(authStore.hasOwnerAccess && !readOnly);
    // A bird record of a domestic bird: moved to Garden when the owner keeps it, otherwise asked about.
    const gardenOwner = $derived(hasOwnerDetectionActions && settingsStore.settings?.beta_garden_animals === true);
    let domesticOptions = $state.raw<DomesticBirdOption[]>([]);
    let movingToGarden = $state(false);
    $effect(() => {
        if (!gardenOwner) return;
        const controller = new AbortController();
        fetchGardenDomesticBirds(controller.signal)
            .then((options) => {
                if (!controller.signal.aborted) domesticOptions = options;
            })
            .catch(() => {
                if (!controller.signal.aborted) domesticOptions = [];
            });
        return () => controller.abort();
    });
    const domesticMatch = $derived(
        gardenOwner && detection && !detection.is_hidden ? domesticBirdForRecord(detection, domesticOptions) : null
    );
    // Rows that come from an integration only appear when that integration is on:
    // "no matching call" from a disabled BirdNET would be a measurement we never took.
    const birdnetEnabled = $derived(
        (settingsStore.settings?.birdnet_enabled ?? authStore.birdnetEnabled ?? false) && authStore.canViewAudio
    );
    const snapshotImageUrl = $derived.by(() => withCacheBust(getSnapshotUrl(detection.frigate_event), snapshotCacheToken));
    const originalFrigateSnapshotUrl = $derived.by(() => withCacheBust(getOriginalFrigateSnapshotUrl(detection.frigate_event), String(snapshotRefreshToken)));
    let canShowFavoriteAction = $derived(
        authStore.canModify
        && !readOnly
        && !reclassifyProgress
    );
    const originalFrigateSnapshotAvailable = $derived(
        snapshotStatus?.original_frigate_snapshot_available === true && !asRecordedDismissed
    );
    const fullFrameSnapshotCandidate = $derived(
        findMatchingFullFrameCandidate(snapshotCandidates, currentSnapshotCandidateId)
    );
    const scanFrameCandidate = $derived(findScanFrameCandidate(snapshotCandidates, currentSnapshotCandidateId, currentSnapshotSource));
    // One owner for the photograph's scan: the row under the photograph and the rail both read it.
    const birdScan = new BirdScan(
        () => hasOwnerDetectionActions
            ? { eventId: detection.frigate_event, candidateId: scanFrameCandidate?.candidate_id ?? null, imageVersion: scanFrameCandidate?.image_url ?? null }
            : null,
        (eventId, candidateId) => { void refreshBirdsAfterScan(eventId, candidateId); }
    );
    /** Why the finder cannot run, when that stands: said after the identification, not under the photograph. */
    const scanStandingText = $derived(birdScan.standingReason ? birdScanUnavailableText(birdScan.standingReason, $_) : null);
    // One thumbnail per moment of the visit; the framings of a moment fold into it (#256).
    // Candidate media is owner-gated, so the strip simply does not exist for a guest.
    const frameMoments = $derived<FrameMoment[]>(
        authStore.hasOwnerAccess
            ? groupCandidatesIntoMoments(
                snapshotCandidates.filter((item) =>
                    item.thumbnail_url || item.image_url || item.candidate_id === currentSnapshotCandidateId
                ),
                { asRecordedAvailable: originalFrigateSnapshotAvailable }
            )
            : []
    );
    const activeMoment = $derived(currentMoment(frameMoments, currentSnapshotCandidateId, currentSnapshotSource));

    // The photograph is always the crop. The whole scene is a look, not a mode (#256): the shared
    // controller peeks on hover or focus with the crop outlined and pins on click, so the one
    // rescue that needs the whole scene can be offered. Persisting anything stays a named action.
    // Frigate's own snapshot has no candidate record, so the "matching" whole frame would be
    // another moment's: different evidence, not a safe peek.
    // A whole scene that failed to load is not offered again; the photograph stays where it was.
    let failedSceneUrls = $state<ReadonlySet<string>>(new Set());
    const wholeSceneSources = $derived(
        // Full resolution only: a scene thumbnail is too small to judge by and cannot carry the outlines.
        [fullFrameSnapshotCandidate?.image_url].filter(
            (url): url is string => !!url && !failedSceneUrls.has(url)
        )
    );
    const canPeekWholeScene = $derived(
        authStore.hasOwnerAccess
        && currentSnapshotSource !== 'frigate_snapshot'
        && wholeSceneSources.length > 0
    );
    const wholeScene = new WholeScenePeek(() => canPeekWholeScene);
    const currentCropCandidate = $derived(
        snapshotCandidates.find((candidate) => candidate.candidate_id === currentSnapshotCandidateId)
            ?? snapshotCandidates.find((candidate) => candidate.selected)
            ?? null
    );
    const wholeSceneCrops = $derived(sameFrameCropCandidates(snapshotCandidates, currentCropCandidate));
    // The saved photograph, then the camera's thumbnail of the same capture, then a placeholder:
    // a working picture is never given up for a missing one. The ambient wash follows whichever
    // one is actually drawn.
    const photographSources = $derived([
        snapshotImageUrl,
        getThumbnailUrl(detection.frigate_event, settledMediaVersion)
    ]);
    /** A crop fills the frame; a whole scene is shown whole. Its scene failing does not change that. */
    const photographIsCrop = $derived(
        authStore.hasOwnerAccess && currentSnapshotSource !== 'frigate_snapshot' && !!fullFrameSnapshotCandidate
    );
    let photographDrawnUrl = $state<string | null>(null);
    let photographFit = $state<PhotoFit>('cover');
    let sceneImageEl = $state<HTMLImageElement | null>(null);
    /** The scene URL that has finished drawing; until then the photograph stays visible beneath. */
    let sceneLoadedUrl = $state<string | null>(null);
    const wholeSceneReady = $derived(
        wholeScene.showing && sceneLoadedUrl !== null && sceneLoadedUrl === wholeSceneSources[0]
    );
    // A whole scene the owner removed from the photo choices can still be looked at, but not saved.
    const canUseWholeScene = $derived(wholeScene.pinned && wholeSceneReady && !fullFrameSnapshotCandidate?.photo_hidden);

    function wholeSceneLoaded(image: HTMLImageElement): void {
        sceneLoadedUrl = image.getAttribute('src');
        measureWholeScene();
    }

    function wholeSceneFailed(url: string): void {
        failedSceneUrls = new Set([...failedSceneUrls, url]);
        if (wholeSceneSources.length === 0) wholeScene.reset();
    }

    $effect(() => {
        // A new detection starts on its own stored frame.
        void detection.frigate_event;
        wholeScene.reset();
        untrack(() => {
            failedSceneUrls = new Set();
            photographDrawnUrl = null;
            photographFit = 'cover';
        });
    });
    // The outlines are DOM measurements, taken once the whole scene has loaded and again when
    // the window changes size.
    function measureWholeScene() {
        // Crop boxes are frame pixels; only the full-resolution scene shares them, never its thumbnail.
        const sceneUrl = fullFrameSnapshotCandidate?.image_url;
        if (!sceneUrl || !sceneImageEl || sceneImageEl.getAttribute('src') !== sceneUrl) {
            wholeScene.outline = null;
            wholeScene.otherOutlines = [];
            return;
        }
        const otherCropBoxes = wholeSceneCrops.slice(1).flatMap((candidate) =>
            candidate.crop_box ? [candidate.crop_box] : []
        );
        wholeScene.measure(sceneImageEl, wholeSceneCrops[0]?.crop_box, otherCropBoxes);
    }
    $effect(() => {
        if (!wholeScene.showing) {
            wholeScene.outline = null;
            wholeScene.otherOutlines = [];
            sceneLoadedUrl = null;
            return;
        }
        measureWholeScene();
        window.addEventListener('resize', measureWholeScene);
        // The frame also changes size while the window does not: pinning the scene makes room under
        // the photograph for its action, and the outlines have to follow the picture.
        const frame = sceneImageEl;
        const observer = frame ? new ResizeObserver(measureWholeScene) : null;
        if (frame) observer?.observe(frame);
        return () => {
            window.removeEventListener('resize', measureWholeScene);
            observer?.disconnect();
        };
    });
    onDestroy(wholeScene.destroy);
    const canGenerateSnapshotCandidates = $derived(
        !snapshotApplyPending
        && !snapshotGeneratePending
        && Boolean(snapshotStatus?.high_quality_bird_crop_enabled)
    );
    // The record stacks (photograph, then details) on a phone or tablet held upright; from 1024px, or
    // held sideways on a short screen, the two stand side by side. Stacked, the visit's frames and the
    // finder follow the identification instead of standing between it and the photograph.
    const recordSideBySide = new MediaQuery('(min-width: 1024px), ((min-width: 640px) and (max-height: 640px))', true);
    const recordStacked = $derived(!recordSideBySide.current);
    // Held sideways on a phone or small tablet the photograph stands alone in its column, and the
    // identification heads the column beside it.
    const recordShortLandscape = new MediaQuery('(min-width: 640px) and (max-width: 1023.98px) and (max-height: 640px)', false);
    // What stands under the photograph down to the identification buttons, in rem, so the photograph
    // can leave room for it on the first screen (`record-photo-cap`): the column's margins and the
    // identification with its score and buttons; the visit's frames, where the record has them; and
    // the one action a pinned whole scene adds. Nothing here waits on a read except the pin, which
    // is the reader's own act, so the frame does not change size while the record loads.
    // The star, play and "Back to the crop" float on the photograph's lower edge: a label on the
    // picture keeps clear of this much of its foot.
    const PHOTOGRAPH_CONTROLS_ROOM = 64;
    const RECORD_UNDER_PHOTO = { decision: 18.5, frames: 7.5, sceneAction: 3.5 };
    const recordUnderPhotoRem = $derived(
        RECORD_UNDER_PHOTO.decision
        + (hasOwnerDetectionActions && hasFrameSource ? RECORD_UNDER_PHOTO.frames : 0)
        + (wholeScene.pinned ? RECORD_UNDER_PHOTO.sceneAction : 0)
    );
    const showInlineFramePicker = $derived(
        hasOwnerDetectionActions
        && hasFrameSource
        && !reclassifyProgress
        && (
            snapshotCandidatesLoading
            || frameMoments.length > 0
            || canGenerateSnapshotCandidates
            || undoablePhotoRemoval === detection.frigate_event
        )
    );

    const UNKNOWN_SPECIES_LABELS = new Set(['unknown', 'unknown bird', 'background']);
    const isUnknownSpecies = $derived(UNKNOWN_SPECIES_LABELS.has((detection.display_name || '').trim().toLowerCase()));
    // A named species brings its family tree and reference, enough for a column of their own.
    // Without a name there is neither, and the record is one narrow column, not a wide box with an
    // empty side. The shape is decided from what the record holds when it opens, never from a read
    // that has yet to answer, so the dialog does not change width while it loads.
    const recordHasReference = $derived(!isUnknownSpecies && Boolean(detection.scientific_name));

    // "Gone" needs a not-found answer; a Frigate that could not be asked gets its own words.
    const frigateReading = $derived(frigateEventReading(detection));
    const missingEventMetadataGone = $derived(!isManualObservation && frigateReading === 'gone');
    const frigateIssueBadgeVisible = $derived(hasFrigateMediaIssue(detection) && !missingEventMetadataGone);
    const upstreamMissing = $derived(!isManualObservation && detection.frigate_status === 'missing');
    const missingEventNoticeVisible = $derived(
        !isManualObservation && frigateEventNotice(frigateReading, $_) !== null
    );
    // The originating Frigate event, for the owner only: frigate_url travels
    // on the owner-only settings payload and never reaches a guest, and a
    // retired event gets words instead of a link that lands on an error (#309).
    // The public URL wins when set, because frigate_url is often a container
    // address the browser cannot reach.
    const frigateEventUrl = $derived.by(() => {
        if (!hasOwnerDetectionActions || isManualObservation) return null;
        if (missingEventMetadataGone) return null;
        const base = settingsStore.settings?.frigate_external_url || settingsStore.settings?.frigate_url;
        if (!base || !detection.frigate_event) return null;
        return `${base.replace(/\/$/, '')}/explore?event_id=${encodeURIComponent(detection.frigate_event)}`;
    });
    const videoFailureInsight = $derived.by(() => getVideoFailureInsight(detection, $_));
    const videoClassificationDiagnostics = $derived(detection.video_classification_diagnostics ?? null);
    const videoAnalysisAbstained = $derived.by(() => {
        const error = (detection.video_classification_error || '').trim().toLowerCase();
        return error === 'video_no_results'
            || error === 'snapshot_no_results'
            || error === 'snapshot_no_usable_result'
            || error === 'no_confident_result';
    });

    // Consolidated video-status notice: single source of truth that replaces
    // the three overlapping panels (Frigate-event-missing pill, "Result from
    // snapshot" amber notice, "Video Analysis Failed" red card) that used to
    // co-exist for the same underlying state.
    const videoStatusNoticeVisible = $derived.by(() => {
        return shouldShowVideoStatusNotice(detection, missingEventNoticeVisible);
    });
    // Fail is kept for a video that failed with nothing recovered to fall back on. When the snapshot
    // already gave a real result, a confident one is neutral and a borderline one needs attention.
    const videoStatusNoticeTone = $derived.by((): 'fail' | 'attention' | 'neutral' => {
        const status = (detection.video_classification_status || '').trim().toLowerCase();
        if (status === 'failed' && !videoAnalysisAbstained && currentClassificationSource !== 'snapshot') return 'fail';
        return Number(detection.score ?? 0) >= 0.8 ? 'neutral' : 'attention';
    });
    const videoStatusNoticeTitle = $derived.by(() => {
        const status = (detection.video_classification_status || '').trim().toLowerCase();
        if (status === 'failed' && videoAnalysisAbstained) {
            return $_('detection.reclassification.unchanged_title', { default: 'Identification unchanged' });
        }
        if (status === 'failed' && currentClassificationSource !== 'snapshot') {
            return $_('detection.video_analysis.failed_title');
        }
        return $_('detection.video_analysis.fallback_title', { default: 'Classified from snapshot' });
    });
    const videoStatusNoticeDescription = $derived.by(() => {
        const error = (detection.video_classification_error || '').trim();
        if (videoAnalysisAbstained) {
            return $_('detection.reclassification.unchanged_description', {
                default: 'No result cleared the confidence rules, so the existing identification was kept.'
            });
        }
        if (error) {
            return formatSnapshotFallbackReason(
                error,
                $_,
                $_('detection.video_analysis.fallback_desc', {
                    default: 'Video analysis was not available, so this capture was named from a single frame. The score may be lower.'
                })
            );
        }
        // No error code: say what was learned about the event in Frigate, and no more than that.
        return frigateEventNotice(frigateReading, $_) ?? '';
    });
    // Technical details exist only for a recorded error or diagnostics. Without either there is
    // no error to detail, and the generic "video analysis failed" causes would be invented.
    const videoStatusShowTechnicalDetails = $derived(
        Boolean((detection.video_classification_error || '').trim()) || Boolean(videoClassificationDiagnostics)
    );

    async function loadCommonNameOverride(scientificName: string) {
        commonNameOverrideLoadedFor = scientificName;
        commonNameEditorOpen = false;
        try {
            const result = await fetchCommonNameOverride(scientificName);
            if (commonNameOverrideLoadedFor !== scientificName) return;
            commonNameOverride = result.manual_common_name ?? null;
            commonNameOverrideInput = result.manual_common_name ?? result.effective_common_name ?? '';
        } catch {
            if (commonNameOverrideLoadedFor !== scientificName) return;
            commonNameOverride = null;
            commonNameOverrideInput = detection.common_name ?? '';
        }
    }

    async function saveCommonNameOverride() {
        const scientificName = detection.scientific_name?.trim();
        const commonName = commonNameOverrideInput.trim();
        if (!scientificName || !commonName || commonNameOverrideSaving) return;
        commonNameOverrideSaving = true;
        try {
            const result = await setCommonNameOverride(scientificName, commonName);
            commonNameOverride = result.manual_common_name ?? null;
            commonNameOverrideInput = result.effective_common_name ?? commonName;
            detection.common_name = result.effective_common_name ?? undefined;
            detectionsStore.updateDetection({ ...detection });
            commonNameEditorOpen = false;
            toastStore.success($_('detection.common_name_override_saved', { default: 'Common name updated' }));
        } catch (error) {
            toastStore.error(getErrorMessage(error) || $_('common.error', { default: 'Action failed' }));
        } finally {
            commonNameOverrideSaving = false;
        }
    }

    async function resetCommonNameOverride() {
        const scientificName = detection.scientific_name?.trim();
        if (!scientificName || commonNameOverrideSaving) return;
        commonNameOverrideSaving = true;
        try {
            const result = await clearCommonNameOverride(scientificName);
            commonNameOverride = null;
            commonNameOverrideInput = result.effective_common_name ?? '';
            detection.common_name = result.effective_common_name ?? undefined;
            detectionsStore.updateDetection({ ...detection });
            commonNameEditorOpen = false;
            toastStore.success($_('detection.common_name_override_cleared', { default: 'Provider common name restored' }));
        } catch (error) {
            toastStore.error(getErrorMessage(error) || $_('common.error', { default: 'Action failed' }));
        } finally {
            commonNameOverrideSaving = false;
        }
    }

    $effect(() => {
        const scientificName = detection.scientific_name?.trim();
        if (!hasOwnerDetectionActions || !scientificName) {
            commonNameOverrideLoadedFor = null;
            commonNameOverride = null;
            commonNameEditorOpen = false;
            return;
        }
        if (commonNameOverrideLoadedFor !== scientificName) {
            void loadCommonNameOverride(scientificName);
        }
    });

    // Searching starts when the owner opens the species picker, not when a record opens.
    let searchTimeout: ReturnType<typeof setTimeout> | undefined;
    $effect(() => {
        if (!hasOwnerDetectionActions || !showTagDropdown) return;
        const query = tagSearchQuery.trim();
        if (query.length === 0) {
            clearTimeout(searchTimeout);
            isSearching = true;
            (async () => {
                try {
                    searchResults = await fetchFeederSpecies();
                } catch (e) {
                    console.error("Search failed", e);
                    // The raw classifier labels stand in only when the catalogue search fails, so they are read then.
                    searchResults = await classifierLabelsStore.searchFallback('', 20);
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
                const searchOptions = getManualTagSearchOptions(query);
                searchResults = await searchSpecies(query, searchOptions.limit, searchOptions.hydrateMissing);
            } catch (e) {
                console.error("Search failed", e);
                searchResults = await classifierLabelsStore.searchFallback(query);
            } finally {
                isSearching = false;
            }
        }, 300);
    });

    onDestroy(() => {
        if (searchTimeout) {
            clearTimeout(searchTimeout);
            searchTimeout = undefined;
        }
    });

    function formatWindDirection(deg?: number | null): string {
        const point = compassPointKey(deg);
        return point ? $_(`common.compass.${point}`, { default: point.toUpperCase() }) : '';
    }

    // The stored condition is the backend's English word; the reader gets it in their language.
    function conditionText(stored: string | null | undefined): string {
        const message = weatherConditionMessage(stored);
        if (!message) return '';
        return message.key ? $_(message.key, { default: message.default }) : message.default;
    }

    function formatPrecip(value?: number | null): string {
        return formatPrecipitation(value, weatherUnitSystem, {
            metric: $_('common.unit_mm', { default: 'mm' }),
            imperial: $_('common.unit_in', { default: 'in' })
        });
    }

    const weatherUnitSystem = $derived(
        resolveWeatherUnitSystem(
            settingsStore.settings?.location_weather_unit_system ?? authStore.locationWeatherUnitSystem,
            settingsStore.settings?.location_temperature_unit ?? authStore.locationTemperatureUnit
        )
    );
    const temperatureUnit = $derived(getTemperatureUnitForSystem(weatherUnitSystem));

    // The weather is stated once, in one condensed row (#268). Only measured
    // facts appear; an unknown is omitted rather than shown as a dash.
    const weatherSummary = $derived.by(() => {
        const parts: string[] = [];
        const condition = conditionText(detection.weather_condition);
        const hasTemperature = detection.temperature !== undefined && detection.temperature !== null;
        if (condition || hasTemperature) {
            const temperature = hasTemperature ? formatTemperature(detection.temperature as number, temperatureUnit) : '';
            parts.push([condition, temperature].filter(Boolean).join(' '));
        }
        if (detection.weather_wind_speed !== undefined && detection.weather_wind_speed !== null) {
            const speed = formatWindSpeed(detection.weather_wind_speed, weatherUnitSystem, {
                metric: $_('common.unit_kmh', { default: 'km/h' }),
                imperial: $_('common.unit_mph', { default: 'mph' })
            });
            parts.push(
                [`${$_('detection.weather_wind')}\u00a0${speed}`, formatWindDirection(detection.weather_wind_direction)]
                    .filter(Boolean)
                    .join(' ')
            );
        }
        if (detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null) {
            parts.push(`${$_('detection.weather_cloud')}\u00a0${Math.round(detection.weather_cloud_cover)}%`);
        }
        if (detection.weather_rain !== undefined && detection.weather_rain !== null && detection.weather_rain > 0) {
            parts.push(`${$_('detection.weather_rain')}\u00a0${formatPrecip(detection.weather_rain)}`);
        }
        if (detection.weather_snowfall !== undefined && detection.weather_snowfall !== null && detection.weather_snowfall > 0) {
            parts.push(`${$_('detection.weather_snow')}\u00a0${formatPrecip(detection.weather_snowfall)}`);
        }
        // Measured by a light sensor at the detection (#945); never estimated from the weather.
        const light = formatIlluminance(detection.illuminance_lux);
        if (light !== null) {
            parts.push(`${$_('detection.weather_light', { default: 'Light' })}\u00a0${light}`);
        }
        // Each label is tied to its figure, and each separator to the reading before it, so a wrapped
        // line never splits "Cloud cover" from its percentage or starts with "·".
        return parts.join('\u00a0· ');
    });
    async function handleManualTag(selection: SearchResult) {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly) return;
        if (!detection) return;
        if (updatingTag) return;

        const requestedSpecies = selection.id;
        updatingTag = true;
        pendingManualTagId = requestedSpecies;
        try {
            const result = await updateDetectionSpecies(detection.frigate_event, requestedSpecies);
            const nextDetection = applyManualTagResult(detection, result);
            Object.assign(detection, nextDetection);
            detectionsStore.recordOwnerSpeciesChoice(nextDetection);
            if (result.photo_changed) detectionsStore.notePhotoChanged(detection.frigate_event);
            showTagDropdown = false;
            tagSearchQuery = '';
            const successLabel = $birdNames(nextDetection, showCommon, preferSci).primary;
            if (result.status === 'unchanged') {
                toastStore.success(
                    $_('notifications.species_confirmed', {
                        values: { species: successLabel },
                        default: '{species} confirmed'
                    })
                );
            } else {
                toastStore.success(
                    `${$_('notifications.event_reclassify', { default: 'Reclassification complete' })}: ${successLabel}`
                );
            }
        } catch (e) {
            toastStore.error($_('notifications.reclassify_failed', { values: { message: getErrorMessage(e) } }));
        } finally {
            pendingManualTagId = null;
            updatingTag = false;
        }
    }

    async function handleHide() {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly) return;
        if (!detection) return;
        try {
            const result = await hideDetection(detection.frigate_event);
            detection.is_hidden = result.is_hidden;
            if (result.is_hidden) {
                detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            }
            await onHideSuccess?.(detection.frigate_event, detection.detection_time, result.is_hidden);
            onClose();
        } catch (e) {
            toastStore.error($_('notifications.hide_failed', { values: { message: getErrorMessage(e) } }));
        }
    }

    async function handleMoveToGarden() {
        if (!detection || !domesticMatch?.declared || movingToGarden) return;
        movingToGarden = true;
        try {
            await moveDetectionToGarden(detection.frigate_event);
            detection.is_hidden = true;
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            toastStore.success($_('detection.moved_to_garden', { default: 'Moved to Garden. The bird record is hidden; show it again from Hidden to restore it.' }));
            await onHideSuccess?.(detection.frigate_event, detection.detection_time, true);
            onClose();
        } catch (e) {
            toastStore.error($_('detection.move_to_garden_failed', { default: 'This record could not be moved to Garden. Try again; if it keeps failing, open Health.', values: { message: getErrorMessage(e) } }));
        } finally {
            movingToGarden = false;
        }
    }

    async function handleDelete() {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly) return;
        if (!detection) return;
        if (!(await confirmAction({
            title: $_('actions.delete_detection', { default: 'Delete this visit permanently' }),
            message: $_('actions.confirm_delete', { values: { species: detection.display_name } }),
            confirmLabel: $_('dashboard.review_session.delete', { default: 'Delete permanently' })
        }))) return;

        try {
            await deleteDetection(detection.frigate_event);
            detectionsStore.removeDetection(detection.frigate_event, detection.detection_time);
            await onDeleteSuccess?.(detection.frigate_event, detection.detection_time);
            onClose();
        } catch (e) {
            toastStore.error($_('notifications.delete_failed', { values: { message: getErrorMessage(e) } }));
        }
    }

    async function handleFavoriteToggle() {
        if (readOnly) return;
        if (!detection) return;
        favoritePending = true;
        try {
            if (detection.is_favorite) {
                // Unfavouriting removes the archive with it; say so before doing it (#178).
                const archivedBytes = archiveStatusHere?.bytes ?? 0;
                if (archivedBytes > 0) {
                    const confirmed = await confirmAction({
                        title: $_('detection.unfavorite_button', { default: 'Remove favourite' }),
                        message: $_('detection.unfavorite_confirm', {
                            values: { size: formatArchiveSize(archivedBytes) },
                            default: 'Remove the favourite? Its archived photo and clip ({size}) go with it. The visit stays in history.'
                        }),
                        confirmLabel: $_('detection.unfavorite_button', { default: 'Remove favourite' })
                    });
                    if (!confirmed) return;
                }
                await unfavoriteDetection(detection.frigate_event);
                detection.is_favorite = false;
                detection.archive_state = null;
                archiveStatus = null;
                detectionsStore.updateDetection({ ...detection, is_favorite: false, archive_state: null });
                toastStore.success($_('detection.favorite_removed', { default: 'Removed from favourites' }));
            } else {
                const result = await favoriteDetection(detection.frigate_event);
                detection.is_favorite = true;
                detection.archive_state = asArchiveState(result.archive_state) ?? 'pending';
                detectionsStore.updateDetection({ ...detection, is_favorite: true, archive_state: detection.archive_state });
                toastStore.success($_('detection.favorite_added', { default: 'Added to favourites' }));
            }
        } catch (e) {
            toastStore.error(getErrorMessage(e) || $_('common.error', { default: 'Action failed' }));
        } finally {
            favoritePending = false;
        }
    }

    function resetMediaView() {
        wholeScene.reset();
    }

    async function useWholeSceneAsPhotograph() {
        const candidate = fullFrameSnapshotCandidate;
        if (!candidate) return;
        await handleApplySnapshot('candidate', candidate.candidate_id);
    }

    interface PhotoRequestRecord {
        eventId: string;
        species: string;
        time: string;
    }

    /** The record a photo request is for, named while it is still the open one. */
    function photoRequestRecord(): PhotoRequestRecord {
        return {
            eventId: detection.frigate_event,
            species: $birdNames(detection, showCommon, preferSci).primary,
            time: formatDateTime(detection.detection_time)
        };
    }

    /** A failure is always reported; after a switch it names its record, so it is not read as the open one's. */
    function reportPhotoRequestFailure(record: PhotoRequestRecord, error: unknown): void {
        const message = getErrorMessage(error) || $_('common.error', { default: 'Action failed' });
        if (detection?.frigate_event === record.eventId) {
            toastStore.error(message);
            return;
        }
        toastStore.error(
            $_('detection.photo_request_failed_for_record', {
                values: { species: record.species, time: record.time, message },
                default: 'The photo of {species} at {time} was not changed. {message}'
            })
        );
    }

    /** Removes or restores every candidate behind one strip choice, and says which removals changed. */
    async function removePhotoChoice(
        candidateIds: string[],
        dismissed: boolean,
        expectedContentIdentities?: Record<string, string>
    ): Promise<SnapshotDismissalTarget[]> {
        const [candidateId, ...companionCandidateIds] = candidateIds;
        if (!candidateId || !hasOwnerDetectionActions || snapshotApplyPending) return [];
        const record = photoRequestRecord();
        const eventId = record.eventId;
        photoApplyEvents.add(eventId);
        try {
            const response = await dismissSnapshotCandidate(eventId, candidateId, dismissed, {
                companionCandidateIds,
                expectedContentIdentities
            });
            if (detection.frigate_event === eventId && hasOwnerDetectionActions) {
                candidateListRevision += 1;
                snapshotCandidates = response.candidates;
                asRecordedDismissed = Boolean(response.as_recorded_dismissed);
                currentSnapshotCandidateId = response.current_candidate_id ?? null;
                currentSnapshotSource = response.current_source ?? currentSnapshotSource;
                snapshotCandidatesError = false;
                undoablePhotoRemoval = dismissed ? eventId : null;
            }
            return response.changed_dismissals ?? [];
        } catch (error) {
            reportPhotoRequestFailure(record, error);
            throw error;
        } finally {
            photoApplyEvents.delete(eventId);
        }
    }

    async function handleUseMoment(moment: FrameMoment) {
        if (!hasOwnerDetectionActions || snapshotApplyPending) return;
        const eventId = detection.frigate_event;
        applyingMoment = { eventId, key: moment.key };
        try {
            if (moment.asRecorded) {
                if (!originalFrigateSnapshotAvailable) return;
                await handleApplySnapshot('revert_original');
                return;
            }
            const candidate = preferredCandidate(moment);
            if (!candidate) return;
            await handleApplySnapshot('candidate', candidate.candidate_id);
        } finally {
            if (applyingMoment?.eventId === eventId) applyingMoment = null;
        }
    }

    async function handleApplySnapshot(
        mode: 'candidate' | 'revert_original',
        candidateId?: string | null
    ) {
        if (!authStore.hasOwnerAccess || readOnly || !detection || snapshotApplyPending) return;
        const record = photoRequestRecord();
        const eventId = record.eventId;
        photoApplyEvents.add(eventId);
        try {
            const result = await applySnapshotCandidate(eventId, {
                mode,
                candidate_id: candidateId ?? null
            });
            detectionsStore.notePhotoChanged(eventId);
            if (!detection || detection.frigate_event !== eventId) return;
            snapshotStatus = result;
            snapshotRefreshToken = Date.now();
            currentSnapshotSource = result.source ?? null;
            currentSnapshotCandidateId = result.applied_candidate_id ?? null;
            resetMediaView();
            toastStore.success($_('detection.snapshot_apply_success', { default: 'Snapshot updated' }));
            await refreshSnapshotControls(eventId);
        } catch (e) {
            reportPhotoRequestFailure(record, e);
        } finally {
            photoApplyEvents.delete(eventId);
        }
    }

    async function refreshBirdsAfterScan(eventId: string, candidateId: string): Promise<void> {
        if (detection.frigate_event !== eventId || scanFrameCandidate?.candidate_id !== candidateId || !hasOwnerDetectionActions) return;
        const epoch = snapshotControlsEpoch;
        countedBirdsLoading = true;
        untrack(() => { countedBirdsGeneration += 1; });
        try {
            const response = await fetchSnapshotCandidates(eventId);
            if (detection.frigate_event !== eventId || snapshotControlsEpoch !== epoch || scanFrameCandidate?.candidate_id !== candidateId || !hasOwnerDetectionActions) return;
            countedBirds = response.birds ?? [];
            countedBirdsError = false;
            countedBirdsGeneration += 1;
            onbirdschanged?.();
        } catch {
            if (detection.frigate_event === eventId && snapshotControlsEpoch === epoch) countedBirdsError = true;
        } finally {
            if (detection.frigate_event === eventId && snapshotControlsEpoch === epoch) countedBirdsLoading = false;
        }
    }

    async function handleGenerateSnapshotCandidates() {
        if (!authStore.hasOwnerAccess || readOnly || !detection || snapshotGeneratePending) return;
        const record = photoRequestRecord();
        const eventId = record.eventId;
        photoGenerateEvents.add(eventId);
        try {
            const result = await generateHighQualityBirdCropSnapshot(eventId);
            // The photo changed whichever record is open now, so its thumbnails elsewhere refresh.
            detectionsStore.notePhotoChanged(eventId);
            if (!detection || detection.frigate_event !== eventId) return;
            snapshotStatus = result;
            snapshotRefreshToken = Date.now();
            await refreshSnapshotControls(eventId);
            if (!detection || detection.frigate_event !== eventId) return;
            // Regeneration can recount the birds, so the log's summary is reread too.
            onbirdschanged?.();
            resetMediaView();
            if (result.status === 'existing_crop_preserved') {
                toastStore.warning($_('detection.snapshot_existing_crop_preserved', { default: 'No reliable new crop was found; the existing crop was kept.' }));
            } else if (result.status === 'manual_selection_preserved') {
                toastStore.warning($_('detection.snapshot_manual_choice_kept', { default: 'Your chosen photo was kept, so no new photo was saved. Regenerate again or choose another photo to replace it.' }));
            } else if (result.status === 'photo_settings_unreadable') {
                toastStore.warning($_('detection.snapshot_settings_unreadable', { default: 'The photo was kept because its saved settings could not be read. Choose a photo for this record to replace it.' }));
            } else if (result.status === 'generated_hq_snapshot') {
                toastStore.warning($_('detection.snapshot_generated_full_frame', { default: 'No reliable crop was found; the best full frame was saved.' }));
            } else if (snapshotCandidates.length > 0 && countedBirds.length > 0 && !snapshotCandidatesError) {
                toastStore.success($_('detection.snapshot_scan_count', {
                    values: { count: countedBirds.filter(bird => !bird.is_hidden).length },
                    default: 'Snapshot scan finished. Current bird count: {count}.'
                }));
            } else if (snapshotCandidates.length > 0) {
                toastStore.success($_('detection.snapshot_generate_success', { default: 'Snapshots regenerated' }));
            } else {
                toastStore.warning($_('detection.snapshot_regenerate_no_candidates', { default: 'Snapshot regenerated, but no selectable candidates were produced.' }));
            }
        } catch (e) {
            reportPhotoRequestFailure(record, e);
        } finally {
            photoGenerateEvents.delete(eventId);
        }
    }

    function handleFetchFullVisitClick(event: Event) {
        event.preventDefault();
        event.stopPropagation();
        onFetchFullVisit?.(detection);
    }

    function handleReclassifyClick() {
        if (!authStore.hasOwnerAccess) return;
        if (readOnly || !onReclassify) return;
        awaitingReclassifyOverlay = true;
        onReclassify(detection);
    }

    $effect(() => {
        if (reclassifyProgress) {
            awaitingReclassifyOverlay = false;
            return;
        }
        if (!videoAnalysisActive) {
            awaitingReclassifyOverlay = false;
        }
    });

    // The band under the photograph holds only actions; with none to show it takes no room, so the
    // photograph is not left floating above an empty dark strip.
    const mediaFooterHasActions = $derived(
        (wholeScene.pinned && wholeSceneReady) ||
            canShowFavoriteAction ||
            canPlayVideo ||
            showFetchFullVisitAction ||
            isManualObservation ||
            frigateIssueBadgeVisible
    );

    function handleSpeciesInfo() {
        onViewSpecies(detection.display_name);
        onClose();
    }
</script>

{#snippet visitStrip()}
    {#if showInlineFramePicker}
        <!-- One ordered strip of the visit's moments (#256). Where a frame came from is not
             shown; choosing one changes the photograph and nothing else. -->
        <div data-detection-inline-frame-picker>
            <FrameStrip
                moments={frameMoments}
                current={activeMoment}
                {primaryName}
                loading={snapshotCandidatesLoading}
                applyingKey={applyingMomentKey}
                busy={snapshotApplyPending || snapshotGeneratePending}
                asRecordedUrl={originalFrigateSnapshotAvailable ? originalFrigateSnapshotUrl : null}
                photographUrl={snapshotImageUrl}
                canRegenerate={Boolean(snapshotStatus?.high_quality_bird_crop_enabled)}
                regeneratePending={snapshotGeneratePending}
                eventId={detection.frigate_event}
                onremove={hasOwnerDetectionActions ? removePhotoChoice : undefined}
                onuse={(moment) => { void handleUseMoment(moment); }}
                onregenerate={() => { void handleGenerateSnapshotCandidates(); }}
            />
        </div>
    {/if}
{/snippet}

{#snippet decision()}
            <!-- The identification and what it rests on: the decision first. -->
            <div class="flex min-w-0 flex-col gap-5 wrap-break-word lg:gap-4 {recordShortLandscape.current ? '' : 'p-5 sm:p-6 lg:p-0'} {showTagDropdown ? 'blur-xs pointer-events-none select-none' : ''}" data-detection-primary-column>
            <div class="flex min-w-0 flex-col gap-5 {recordShortLandscape.current ? '' : 'lg:panel-raised lg:p-5'}" data-detection-decision-panel>
            {#if isManualObservation && detection.observation_notes}
                <div class="border-l-2 border-accent-line pl-3">
                    <div class="text-3xs font-semibold text-muted">{$_('detection.observation_notes', { default: 'Observation notes' })}</div>
                    <p class="mt-1 whitespace-pre-wrap text-sm leading-6 text-ink">{detection.observation_notes}</p>
                </div>
            {/if}
            {#if isManualObservation && detection.observation_latitude != null && detection.observation_longitude != null}
                <div data-manual-observation-location class="border-l-2 border-line pl-3">
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <div class="text-3xs font-semibold text-muted">{$_('manual_observation.location.title', { default: 'Sighting location' })}</div>
                            <p class="mt-1 text-xs tabular-nums text-muted">{detection.observation_latitude.toFixed(5)}, {detection.observation_longitude.toFixed(5)}</p>
                        </div>
                        {#if detection.observation_location_source === 'image_metadata'}
                            <span class="rounded-full bg-surface-raised px-2.5 py-1 text-3xs font-semibold text-muted">{$_('manual_observation.location.from_image', { default: 'From image metadata' })}</span>
                        {/if}
                    </div>
                    <div class="mt-3 h-44 overflow-hidden rounded-xl">
                        <Map
                            markers={[{ lat: detection.observation_latitude, lng: detection.observation_longitude, title: naming.primary }]}
                            center={[detection.observation_latitude, detection.observation_longitude]}
                            zoom={14}
                        />
                    </div>
                </div>
            {/if}
            <!-- Identification: what it is, and how sure, in one place -->
            <div data-detection-identity>
                <div class="flex items-start gap-3">
                    {#if speciesInfo?.thumbnail_url}
                        <!-- A reference photograph of the species, so the camera frame has something
                             to be compared against without leaving the view. -->
                        {#if failedSpeciesReferenceUrl === speciesInfo.thumbnail_url}
                            <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-line bg-surface-raised text-muted" aria-hidden="true" data-detection-species-reference-placeholder>
                                <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M4 18 9 13l3 3 2-2 6 6M15 8h.01M5 4h14a1 1 0 0 1 1 1v14H4V5a1 1 0 0 1 1-1Z" stroke-linecap="round" stroke-linejoin="round" /></svg>
                            </span>
                        {:else}
                            <img
                                src={speciesInfo.thumbnail_url}
                                alt={$_('detection.species_reference_alt', {
                                    values: { species: primaryName },
                                    default: 'Reference photograph of {species}'
                                })}
                                loading="lazy"
                                onerror={() => { failedSpeciesReferenceUrl = speciesInfo?.thumbnail_url ?? null; }}
                                class="h-12 w-12 shrink-0 rounded-full border border-line bg-surface-raised object-cover"
                                data-detection-species-reference
                            />
                        {/if}
                    {/if}
                    <div class="min-w-0">
                        <p class="flex items-center gap-1.5 text-3xs font-semibold text-muted">
                        {#if currentClassificationSource === 'manual'}
                            <svg class="h-3.5 w-3.5 text-status-ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="m5 13 4 4L19 7" />
                            </svg>
                            {authStore.hasOwnerAccess
                                ? $_('detection.identified_by_you', { default: 'Identified by you' })
                                : $_('detection.identified_by_owner', { default: 'Identified by the owner' })}
                        {:else}
                            {$_('detection.identified_as', { default: 'Identified as' })}
                        {/if}
                        </p>
                        <h3 id="detection-modal-title" class="font-display text-2xl font-bold text-strong">{primaryName}</h3>
                        {#if hasOwnerDetectionActions}
                            <ClassificationSource evidence={detection.classification_input} />
                            {#if detection.initial_classification_input && JSON.stringify(detection.initial_classification_input) !== JSON.stringify(detection.classification_input)}
                                <details class="group/original mt-1 text-xs text-muted" data-initial-classification-source>
                                    <summary class="cursor-pointer min-h-11 flex items-center gap-2 rounded-sm focus-visible:ring-2 focus-visible:ring-focus"><svg class="h-3 w-3 group-open/original:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>{$_('detection.named_from.original', { default: 'Original identification' })}</summary>
                                    <ClassificationSource evidence={detection.initial_classification_input} />
                                </details>
                            {/if}
                        {/if}
                        {#if subName && subName !== primaryName}
                            <p class="text-xs italic text-muted">{subName}</p>
                        {/if}
                        <!-- Reads as a link beside the name it is about, not as a button competing with the decisions. -->
                        <button
                            type="button"
                            onclick={handleSpeciesInfo}
                            class="inline-flex min-h-11 items-center gap-1 rounded-sm text-xs font-semibold text-accent-ink underline underline-offset-2 hover:text-accent-ink focus-ring"
                            data-detection-species-details
                        >
                            {$_('actions.species_info')}
                            <svg class="h-3 w-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14m-6-6 6 6-6 6" /></svg>
                        </button>
                    </div>
                </div>

                {#if currentClassificationSource !== 'manual'}
                    <div class="mt-2 flex flex-wrap items-center gap-2.5">
                        <span class="text-sm font-semibold tabular-nums text-strong">
                            {Math.round((detection.score || 0) * 100)}%
                        </span>
                        <span class="text-xs text-muted">
                            {$_('detection.fact_species_match', { default: 'Species match' })} &middot;
                            {scoreBand(detection.score) === 'high'
                                ? $_('detection.confidence_high', { default: 'confident' })
                                : scoreBand(detection.score) === 'mid'
                                  ? $_('detection.confidence_mid', { default: 'likely' })
                                  : $_('detection.confidence_low', { default: 'uncertain' })}
                        </span>
                        <span class="h-1.5 flex-1 overflow-hidden rounded-full bg-track">
                            <span
                                class="block h-full rounded-full {SCORE_FILL[scoreBand(detection.score)]}"
                                data-record-score-bar
                                style="width: {(detection.score || 0) * 100}%"
                            ></span>
                        </span>
                    </div>
                {/if}
            </div>

            <!-- One decision and its alternative sit directly under the identification. Everything
                 else an owner can do waits behind More actions, so two buttons never compete with six. -->
            {#if hasOwnerDetectionActions}
                <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-start" data-detection-identification-actions>
                    {#if !detection.manual_tagged && !isUnknownSpecies}
                        <!-- Takes its label's width, so the label only wraps when it is longer than the row. -->
                        <button
                            type="button"
                            onclick={() => handleManualTag({
                                id: detection.display_name,
                                display_name: detection.display_name,
                                scientific_name: detection.scientific_name ?? null,
                                common_name: detection.common_name ?? null
                            } as SearchResult)}
                            disabled={updatingTag}
                            class="btn btn-primary min-h-11 w-full min-w-0 max-w-full px-4 text-sm sm:w-auto sm:flex-none"
                            data-detection-confirm
                        >
                            <span class="min-w-0 wrap-anywhere">
                                {updatingTag
                                    ? $_('common.saving')
                                    : $_('actions.confirm_species', {
                                        values: { species: primaryName },
                                        default: 'Confirm {species}'
                                    })}
                            </span>
                        </button>
                    {/if}

                    <button
                        type="button"
                        onclick={() => showTagDropdown = !showTagDropdown}
                        disabled={updatingTag}
                        class="btn btn-secondary min-h-11 w-full min-w-0 max-w-full px-4 text-sm sm:w-auto sm:flex-none"
                        data-detection-pick
                    >
                        <span class="min-w-0 wrap-anywhere">
                            {updatingTag
                                ? $_('common.saving')
                                : $_('actions.pick_species', { default: 'Pick a different species' })}
                        </span>
                    </button>

                    <button
                        type="button"
                        onclick={() => { moreActionsOpen = !moreActionsOpen; }}
                        aria-expanded={moreActionsOpen}
                        aria-controls="detection-more-actions"
                        class="btn btn-ghost min-h-11 w-full min-w-0 max-w-full gap-1.5 px-3 text-sm sm:w-auto sm:flex-none"
                        data-detection-more-actions
                    >
                        <span class="min-w-0 wrap-anywhere">{$_('detection.more_actions', { default: 'More actions' })}</span>
                        <svg class="h-3.5 w-3.5 shrink-0 motion-safe:transition-transform {moreActionsOpen ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6" />
                        </svg>
                    </button>
                </div>
                {#if moreActionsOpen}
                    <!-- A plain list directly under its trigger: each row is one action, named by its effect. -->
                    <!-- shrink-0: it clips its rows to its rounded corners, and a clipped box in this scrolling
                         column would otherwise be squashed and cut its last rows off. -->
                    <ul id="detection-more-actions" class="card-base shrink-0 divide-y divide-line-soft overflow-hidden" data-detection-more-actions-panel>
                        {#if hasFrameSource}
                            <li>
                                <button type="button" onclick={handleReclassifyClick} class="btn btn-ghost min-h-11 w-full justify-start rounded-none px-3 text-sm" title={$_('actions.reclassify')} data-detection-score-again>
                                    <span class="min-w-0 text-left wrap-anywhere">{$_('detection.score_again', { default: 'Score again' })}</span>
                                </button>
                            </li>
                        {/if}
                        {#if scanStandingText}
                            <!-- Not a control while it cannot run: its name and the reason, read in order. -->
                            <li class="px-3 py-2 text-sm" data-detection-scan-unavailable>
                                <p class="font-semibold text-muted">{$_('detection.bird_scan.action', { default: 'Find more birds' })}</p>
                                <p class="text-xs text-muted">{scanStandingText}</p>
                            </li>
                        {/if}
                        {#if detection.scientific_name}
                            <li>
                                <button
                                    type="button"
                                    onclick={() => {
                                        commonNameOverrideInput = commonNameOverride ?? detection.common_name ?? '';
                                        commonNameEditorOpen = !commonNameEditorOpen;
                                    }}
                                    aria-expanded={commonNameEditorOpen}
                                    class="btn btn-ghost min-h-11 w-full justify-start rounded-none px-3 text-sm"
                                >
                                    <span class="min-w-0 text-left wrap-anywhere">{$_('detection.common_name_override_edit', { default: 'Change the common name' })}</span>
                                </button>
                                {#if commonNameEditorOpen}
                                    <div class="flex flex-col gap-2 px-3 pb-3 sm:flex-row">
                                        <input
                                            type="text"
                                            maxlength="120"
                                            bind:value={commonNameOverrideInput}
                                            disabled={commonNameOverrideSaving}
                                            aria-label={$_('detection.common_name_override', { default: 'Common name' })}
                                            class="input-base min-w-0 flex-1"
                                        />
                                        <button
                                            type="button"
                                            onclick={saveCommonNameOverride}
                                            disabled={!commonNameOverrideInput.trim() || commonNameOverrideSaving}
                                            class="btn btn-primary min-h-11 px-3 text-xs"
                                        >
                                            {commonNameOverrideSaving ? $_('common.saving') : $_('common.save')}
                                        </button>
                                        {#if commonNameOverride}
                                            <button
                                                type="button"
                                                onclick={resetCommonNameOverride}
                                                disabled={commonNameOverrideSaving}
                                                class="btn btn-secondary min-h-11 px-3 text-xs"
                                            >
                                                {$_('detection.common_name_override_reset', { default: 'Use provider name' })}
                                            </button>
                                        {/if}
                                    </div>
                                {/if}
                            </li>
                        {/if}
                        <li>
                            <!-- Hide is the reversible one, and its name says which way it will go. -->
                            <button
                                type="button"
                                onclick={handleHide}
                                class="btn btn-ghost min-h-11 w-full justify-start rounded-none px-3 text-sm"
                                title={hideActionLabel}
                                aria-label={hideActionLabel}
                                aria-pressed={detection.is_hidden}
                                data-detection-hide
                            >
                                <span class="min-w-0 text-left hyphens-auto wrap-anywhere">{detection.is_hidden ? $_('actions.unhide', { default: 'Unhide' }) : $_('common.hide', { default: 'Hide' })}</span>
                            </button>
                        </li>
                        <li>
                            <!-- The only red control here. Its words say the visit goes for good. -->
                            <button
                                type="button"
                                onclick={handleDelete}
                                class="btn btn-ghost min-h-11 w-full justify-start rounded-none px-3 text-sm text-status-fail hover:bg-status-fail-soft hover:text-status-fail "
                                data-detection-delete
                            >
                                <!-- The words on the row are its whole name, so what is read aloud is what is seen. -->
                                <span class="min-w-0 text-left hyphens-auto wrap-anywhere">{$_('actions.delete_detection')}</span>
                            </button>
                        </li>
                    </ul>
                {/if}
                <!-- The finder, with the decision it informs: one row that lines up with the panel. When it
                     cannot run it steps aside for the line under it, which is always present for an owner so
                     that a reason that comes or goes is announced. -->
                <BirdScanControl
                    scan={birdScan}
                    sceneImageUrl={scanFrameCandidate?.image_url ?? null}
                    disabled={snapshotApplyPending || snapshotGeneratePending || countedBirdsLoading}
                    stepAside
                />
                <p class={scanStandingText ? 'text-xs text-muted' : 'sr-only'} role="status" aria-live="polite" data-detection-scan-standing>{#if scanStandingText}<span class="font-semibold text-ink">{$_('detection.bird_scan.action', { default: 'Find more birds' })}:</span> {scanStandingText}{/if}</p>
            {/if}
                <!-- On a phone or tablet held upright the visit's frames come after the identification, so
                     the decision is read first; on their own dark ground, as under the photograph. -->
                {#if recordStacked && showInlineFramePicker}
                    <div class="overflow-hidden rounded-xl bg-media py-3" data-detection-stacked-strip>{@render visitStrip()}</div>
                {/if}
            </div>

            <!-- What the identification rests on, and the facts of the sighting. -->
            <div class="flex min-w-0 flex-col gap-5 {recordShortLandscape.current ? '' : 'lg:panel-raised lg:p-5'}" data-detection-evidence-panel>

            {#if domesticMatch?.declared}
                <div class="card-base space-y-2 p-3 text-sm text-ink" data-detection-domestic-bird>
                    <p>
                        {$_('detection.domestic_bird_declared', {
                            default: 'This is a {bird}, a domestic bird you keep. Move it to Garden to record it as a Garden animal. This bird record is hidden, not deleted.',
                            values: { bird: domesticBirdName(domesticMatch.key, (id, options) => $_(id, options)) }
                        })}
                    </p>
                    <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm" disabled={movingToGarden} onclick={handleMoveToGarden} data-detection-move-to-garden>
                        {movingToGarden ? $_('common.saving') : $_('detection.move_to_garden', { default: 'Move to Garden' })}
                    </button>
                </div>
            {:else if domesticMatch}
                <GardenDomesticSuggestion bird={domesticMatch.key} />
            {/if}

            <!-- Snapshot fallback notice: video analysis failed, result came from a single frame -->
            <!-- Consolidated video-status notice. Single survivor for the three
                 overlapping panels that used to fire on this state (pill +
                 amber "Result from snapshot" + red "Video Analysis Failed").
                 Tone tier:
                  - hidden when video classification completed and the result
                    matches the display name (the happy path)
                  - slate when the snapshot fallback succeeded with high
                    confidence (informational, not alarming)
                  - amber when the snapshot fallback succeeded but confidence
                    is borderline / unknown
                  - rose when video genuinely failed and the snapshot path
                    didn't recover (rare, but actionable)
                 Folds Frigate-event-missing context, the technical details
                 expander, and the snapshot-fallback explanation together. -->


            <!-- Auto-promotion gated notice: video analysis ran successfully but the
                 score didn't clear the auto-promotion floor, so the primary display
                 wasn't updated. Manual reclassify is the documented path here, so we
                 wire the existing handler in directly. -->
            {#if videoPromotionGated && hasOwnerDetectionActions && onReclassify}
                <div class="p-3 rounded-xl bg-status-attention-soft border border-status-attention-line text-status-attention flex items-start gap-3" role="status">
                    <svg class="w-4 h-4 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="16" x2="12" y2="12"/>
                        <line x1="12" y1="8" x2="12.01" y2="8"/>
                    </svg>
                    <div class="flex-1 min-w-0 flex flex-col gap-2">
                        <div class="flex flex-col gap-0.5">
                            <span class="text-3xs font-semibold">
                                {$_('detection.video_analysis.gated_title', { default: 'Video found a match: confirm to apply' })}
                            </span>
                            <span class="text-2xs font-semibold leading-snug">
                                {$_('detection.video_analysis.gated_desc', {
                                    default: 'The video result was not applied because its score is below your minimum confidence floor. Choose Reclassify to apply it anyway, or lower the floor in Settings → Identifying birds.',
                                })}
                            </span>
                        </div>
                        <div>
                            <button
                                type="button"
                                onclick={handleReclassifyClick}
                                class="btn btn-secondary min-h-11 px-3 text-xs"
                                disabled={!!reclassifyProgress || awaitingReclassifyOverlay}
                            >
                                <svg class="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                                    <path d="M3 12a9 9 0 0 1 15-6.7L21 8"/>
                                    <path d="M21 3v5h-5"/>
                                    <path d="M21 12a9 9 0 0 1-15 6.7L3 16"/>
                                    <path d="M3 21v-5h5"/>
                                </svg>
                                {$_('detection.video_analysis.gated_action', { default: 'Reclassify' })}
                            </button>
                        </div>
                    </div>
                </div>
            {/if}

            <!-- Video Classification Results -->
            {#if detection.video_classification_status === 'completed' || (detection.video_classification_label && detection.video_classification_label !== detection.display_name)}
                <div class="p-4 rounded-2xl bg-surface-raised border border-line animate-in fade-in slide-in-from-top-2">
                    <div class="flex items-center justify-between mb-2">
                        <p class="text-3xs font-semibold text-muted">
                            {completedClassificationTitle}
                        </p>
                        {#if detection.video_classification_score}
                            <!-- Plain figures like the identification's own score, so it is never the louder of the two. -->
                            <span class="text-xs font-semibold tabular-nums text-ink">
                                {$_('detection.video_analysis.match', { values: { score: (detection.video_classification_score * 100).toFixed(0) } })}
                            </span>
                        {/if}
                    </div>
                    <p class="text-sm font-semibold text-strong">
                        {detection.video_classification_label === detection.scientific_name
                            ? $birdNames(detection, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary).primary
                            : detection.video_classification_label}
                    </p>
                    {#if detection.video_result_blocked}
                        <p class="text-3xs font-semibold text-ink mt-0.5">
                            {$_('detection.video_analysis.blocked_label', { default: 'Matched a blocked species: not applied' })}
                        </p>
                    {/if}
                    <!-- What ran it and on which device is diagnostics, not record content. -->
                    <p class="mt-1 text-xs text-muted">
                        {completedClassificationDescription}{#if classificationInputLabel}{' '}&middot; {classificationInputLabel}{/if}
                    </p>
                </div>
            {/if}
            {#if videoAnalysisActive && !reclassifyProgress}
                <div class="p-4 rounded-2xl bg-surface border border-line" role="status">
                    <p class="text-xs font-semibold text-muted">
                        {videoAnalysisStatus === 'pending'
                            ? $_('detection.video_analysis.queued', { default: 'Video analysis queued' })
                            : $_('detection.video_analysis.preparing', { default: 'Preparing video analysis' })}
                    </p>
                </div>
            {/if}
            <!-- The standalone "Video Analysis Failed" red card has been folded
                 into the consolidated video-status notice above. -->

            <!-- The facts, as rows rather than four separate boxes -->
            {#if hasOwnerDetectionActions && hasFrameSource}
                {#key detection.frigate_event}
                    <CountedBirds
                        eventId={detection.frigate_event}
                        birds={countedBirds}
                        candidates={snapshotCandidates}
                        photograph={currentSnapshotSource === 'frigate_snapshot' ? null : currentCropCandidate}
                        generation={countedBirdsGeneration}
                        loading={snapshotCandidatesLoading || countedBirdsLoading}
                        error={snapshotCandidatesError || countedBirdsError}
                        regenerating={snapshotGeneratePending}
                        countingAvailable={Boolean(snapshotStatus?.high_quality_bird_crop_enabled)}
                        onretry={() => { void refreshSnapshotControls(detection.frigate_event); }}
                        onchanged={(updated) => { countedBirds = countedBirds.map((bird) => bird.id === updated.id ? updated : bird); onbirdschanged?.(); }}
                        onstale={() => { void refreshSnapshotControls(detection.frigate_event); onbirdschanged?.(); }}
                    />
                {/key}
            {/if}
            <dl class="divide-y divide-line border-y border-line text-xs" data-detection-facts>
                <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                    <dt class="flex items-center gap-2 text-muted">
                        <svg class="h-3.5 w-3.5 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" /><path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" /></svg>
                        {$_('detection.fact_seen', { default: 'Seen' })}
                    </dt>
                    <dd class="min-w-0 max-w-full text-right font-medium text-strong">
                        {formatDateTime(detection.detection_time)} &middot; {detection.camera_name}
                    </dd>
                </div>
                {#if weatherSummary}
                    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2" data-detection-weather-row>
                        <dt class="flex items-center gap-2 text-muted">
                            <svg class="h-3.5 w-3.5 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" /></svg>
                            {$_('detection.fact_conditions', { default: 'Conditions' })}
                        </dt>
                        <!-- Too long for the label's line, so it is a column under the label's words: level
                             with them, not ragged at the right edge. -->
                        <dd class="w-full min-w-0 pl-5.5 text-left font-medium text-strong">
                            {weatherSummary}
                        </dd>
                    </div>
                {/if}
                {#if detection.frigate_score != null}
                    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                        <dt
                            class="flex items-center gap-2 text-muted"
                            title={$_('detection.fact_frigate_hint', {
                                default:
                                    'How sure the camera was that it had seen a bird at all, before the species was worked out. Separate from the species match above, so the two percentages will differ.'
                            })}
                        >
                            <svg class="h-3.5 w-3.5 shrink-0 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2" /></svg>
                            {$_('detection.fact_frigate', { default: 'Spotted as a bird' })}
                        </dt>
                        <dd class="min-w-0 max-w-full text-right font-medium text-strong">
                            {Math.round((detection.frigate_score || 0) * 100)}%
                        </dd>
                    </div>
                {/if}
                {#if birdnetEnabled && !isManualObservation}
                <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                    <dt class="flex items-center gap-2 text-muted">
                        <svg class="h-3.5 w-3.5 shrink-0 text-status-ok" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 3h6v11a3 3 0 01-6 0zM5 11a7 7 0 0014 0M12 18v3" /></svg>
                        {$_('detection.fact_heard', { default: 'Heard nearby' })}
                    </dt>
                    <dd class="min-w-0 max-w-full text-right font-medium {effectiveAudioConfirmed ? 'text-status-ok' : 'text-muted'}">
                        {audioFactValue}
                    </dd>
                </div>
                {/if}
            </dl>

            {#if detection.is_favorite && archiveFailure}
                <!-- What was not kept, why, and what to do, in words: the heading carries the state, not its colour.
                     Until the archive status is read for this record, it claims nothing about what was kept. -->
                <div class="space-y-1 text-sm" data-detection-archive-state="failed" data-detection-archive-view={archiveFailure.kind} aria-live="polite">
                    {#if archiveFailure.kind === 'explained'}
                        <p class="font-semibold text-status-fail">{archiveFailure.lost}</p>
                        <p class="text-ink" data-detection-archive-cause>{archiveFailure.cause}</p>
                        <p class="text-xs text-muted">{archiveFailure.retry}</p>
                        {#if hasOwnerDetectionActions}
                            <button type="button" class="btn btn-secondary mt-1 min-h-11 px-3 text-xs" disabled={archiveRetrying} onclick={() => { void handleArchiveRetry(); }}>
                                {$_('detection.archive_retry_now', { default: 'Try again now' })}
                            </button>
                        {/if}
                    {:else}
                        <p class="text-ink">{archiveFailure.lost}</p>
                        {#if archiveFailure.kind === 'unchecked'}
                            <button type="button" class="btn btn-secondary mt-1 min-h-11 px-3 text-xs" onclick={() => { archiveCheckAttempt += 1; }} data-detection-archive-check-again>
                                {$_('detection.archive_check_again', { default: 'Check again' })}
                            </button>
                        {/if}
                    {/if}
                </div>
            {:else if detection.is_favorite && archiveLabel}
                <!-- A status of the record, so it is said here in words and never drawn over the photograph. -->
                <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-ink" data-detection-archive-state={archiveState} aria-live="polite">
                    {#if archiveState === 'pending'}
                        <span class="inline-block h-3 w-3 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin" aria-hidden="true"></span>
                    {/if}
                    <span>{archiveLabel}</span>
                </p>
            {/if}

            {#if videoStatusNoticeVisible}
                {#key detection.frigate_event}
                    <RecordVideoStatusNotice
                        {detection}
                        tone={videoStatusNoticeTone}
                        title={videoStatusNoticeTitle}
                        description={videoStatusNoticeDescription}
                        insight={videoFailureInsight}
                        {upstreamMissing}
                        showTechnicalDetails={videoStatusShowTechnicalDetails}
                        docsUrl={FRIGATE_MISSING_DOCS_URL}
                    />
                {/key}
            {/if}

            {#if hasAudioContext}
                {#key detection.frigate_event}
                    <RecordAudioEvidence
                        confirmed={effectiveAudioConfirmed}
                        nearbySummary={audioNearbySummary}
                        entry={matchedAudioEntry}
                        calls={audioContext}
                        loading={audioContextLoading}
                        loaded={audioContextLoaded}
                        error={audioContextError}
                        suppressed={audioContextSuppressed}
                    />
                {/key}
            {/if}
            </div>
            </div>
{/snippet}

<div
    data-detection-detail-modal
    class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto overscroll-contain dialog-scrim p-0 backdrop-blur-xs sm:p-4"
    data-theme={isDarkMode ? 'dark' : 'light'}
    onclick={(e) => {
        if (e.target === e.currentTarget) {
            onClose();
        }
    }}
    onkeydown={(e) => {
        if (e.key !== 'Escape') return;
        // A pinned whole scene closes first; the record stays open.
        if (wholeScene.pinned) {
            e.preventDefault();
            resetMediaView();
            return;
        }
        onClose();
    }}
    role="dialog"
    aria-modal="true"
    aria-labelledby="detection-modal-title"
    tabindex="-1"
>
    <div
        bind:this={modalElement}
        data-theme={isDarkMode ? 'dark' : 'light'}
        class="relative flex max-h-dvh w-full max-w-5xl flex-col overflow-hidden rounded-none dialog-surface sm:max-h-[92vh] sm:rounded-2xl {recordHasReference ? 'lg:h-208 xl:max-w-6xl' : 'lg:max-w-xl'}"
        role="document"
        tabindex="-1"
    >

        <!-- Reclassification Overlay (covers entire modal content) -->
        {#if reclassifyProgress}
            <ReclassificationOverlay progress={reclassifyProgress} />
        {/if}

        <!-- The shared dialog header, so nothing scrolls under the close button. The record's heading is
             the species name below, so the strip carries a quiet label rather than a second heading. -->
        <DialogHeader
            label={$_('detection.record_label', { default: 'Record' })}
            onClose={onClose}
            closeData={{ 'data-detection-modal-close': true }}
            data-detection-modal-header
        />

        <!-- From 1024px a record with a reference to read stands in two columns that each scroll: the
             photograph with the decision under it, and the reference beside them. A record with no
             reference is one narrow column. Held sideways on a phone or small tablet (a short screen), the
             photograph stands beside everything else, so the identification is on the first screen. -->
        <div class="flex-1 overflow-y-auto flex flex-col {recordHasReference ? 'lg:grid lg:grid-cols-2 lg:grid-rows-1 lg:overflow-hidden' : 'lg:dialog-well'} sm:max-lg:short:grid sm:max-lg:short:grid-cols-2 sm:max-lg:short:grid-rows-1 sm:max-lg:short:overflow-hidden">
            <div class="flex min-w-0 shrink-0 flex-col lg:gap-4 lg:p-4 {recordHasReference ? 'lg:dialog-well lg:min-h-0 lg:shrink lg:overflow-y-auto lg:border-r lg:border-line' : ''} sm:max-lg:short:min-h-0 sm:max-lg:short:shrink sm:max-lg:short:overflow-y-auto sm:max-lg:short:border-r sm:max-lg:short:border-line" data-detection-evidence-column>
                <!-- The photograph keeps its own shape at the top of its column, with the visit's frames under
                     it, one object on the media ground. It gives up height before the identification under
                     it leaves the first screen. -->
                <div class="flex shrink-0 flex-col bg-media lg:overflow-hidden lg:rounded-2xl lg:media-frame" data-detection-media>
                    <!-- w-full, not only the stretch: with a height cap and an aspect ratio, Safari narrows a
                         stretched box to the cap's width, which left a black band beside the photograph. -->
                    <div class="relative w-full min-w-0 aspect-4/3 min-h-72 shrink-0 overflow-hidden bg-media sm:max-lg:aspect-video lg:min-h-0 short:min-h-0 max-sm:max-lg:short:max-h-half-screen {recordHasReference ? 'lg:record-photo-cap' : 'lg:record-photo-cap-narrow'}" style:--record-under-photo="{recordUnderPhotoRem}rem" data-detection-photograph>
                        {#if photographDrawnUrl}
                            <img data-detection-media-ambient src={photographDrawnUrl} alt="" aria-hidden="true" class="absolute inset-0 h-full w-full scale-110 object-cover opacity-60 blur-2xl" />
                        {/if}
                        <!-- A photograph shown whole stands on a soft fill of its own colours, dimmed enough that
                             the picture stays the brightest thing in its frame; never on black bars. -->
                        <div class="absolute inset-0 bg-media/35" aria-hidden="true"></div>
                        <!-- The photograph stays drawn under a peek, and only steps aside once the whole
                             scene has actually loaded over it. -->
                        <MediaImage
                            sources={photographSources}
                            alt={detection.display_name}
                            class="relative h-full w-full {photographIsCrop && photographFit === 'cover' ? 'object-cover' : 'object-contain'} {wholeSceneReady ? 'opacity-0' : ''}"
                            placeholderClass="text-on-media/80"
                            iconClass="h-10 w-10"
                            onload={(image) => {
                                photographDrawnUrl = image.getAttribute('src');
                                // A tall crop would be cut to a band: it is shown whole over the ambient fill (#481).
                                photographFit = photoFitFor(image);
                            }}
                        />
                        {#if canPeekWholeScene && wholeScene.showing}
                            <MediaImage
                                bind:element={sceneImageEl}
                                sources={wholeSceneSources}
                                alt=""
                                class="absolute inset-0 h-full w-full object-contain {wholeSceneReady ? 'opacity-100' : 'opacity-0'}"
                                placeholderClass="hidden"
                                onload={wholeSceneLoaded}
                                onfail={wholeSceneFailed}
                                data-detection-whole-scene-image
                            />
                        {/if}
                        {#if canPeekWholeScene}
                            <!-- The whole scene is a look, not a mode (#256). Hover or focus peeks at it with
                                 same-frame crops outlined; a click pins it and offers the one rescue that needs it. -->
                            <button
                                type="button"
                                class="absolute inset-0 z-10 {wholeScene.pinned ? 'cursor-zoom-out' : 'cursor-zoom-in'} focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus-on-dark"
                                data-detection-whole-scene-peek
                                aria-pressed={wholeScene.pinned}
                                aria-label={wholeScene.pinned
                                    ? $_('detection.whole_scene_back', { default: 'Back to the crop' })
                                    : $_('detection.whole_scene_show', { default: 'Show the whole scene' })}
                                onmouseenter={wholeScene.enter}
                                onmouseleave={wholeScene.leave}
                                onfocus={wholeScene.show}
                                onblur={wholeScene.leave}
                                onclick={(event) => { event.stopPropagation(); wholeScene.toggle(); }}
                            ></button>
                            {#if wholeSceneReady && wholeScene.outline}
                                <div
                                    class="pointer-events-none absolute z-20 rounded-xs border-2 border-solid border-evidence {wholeScene.otherOutlines.length === 0 ? 'shadow-[0_0_0_9999px_rgba(2,6,23,0.35)]' : ''}"
                                    style="left: {wholeScene.outline.left}px; top: {wholeScene.outline.top}px; width: {wholeScene.outline.width}px; height: {wholeScene.outline.height}px;"
                                    data-detection-whole-scene-outline
                                    aria-hidden="true"
                                ><span class="absolute whitespace-nowrap rounded-sm bg-evidence px-1.5 py-0.5 text-3xs font-semibold text-media {outlineLabelClass(outlineLabelPlace(wholeScene.outline, { width: sceneImageEl?.clientWidth ?? 0, height: sceneImageEl?.clientHeight ?? 0 }, PHOTOGRAPH_CONTROLS_ROOM))}" data-detection-whole-scene-label>{$_('detection.frame_chosen_badge', { default: 'Chosen' })}</span></div>
                                {#each wholeScene.otherOutlines as outline}
                                    <div
                                        class="pointer-events-none absolute z-10 rounded-xs border-2 border-dashed border-on-media/90"
                                        style="left: {outline.left}px; top: {outline.top}px; width: {outline.width}px; height: {outline.height}px;"
                                        data-detection-other-bird-outline
                                        aria-hidden="true"
                                    ></div>
                                {/each}
                            {/if}
                            {#if wholeSceneReady}
                                <span
                                    class="pointer-events-none absolute left-3 top-3 z-30 rounded-full border border-on-media/15 bg-media/70 px-2.5 py-1 text-2xs font-semibold text-on-media backdrop-blur-xs"
                                    data-detection-whole-scene-chip
                                >
                                    {wholeScene.otherOutlines.length > 0
                                        ? $_('detection.whole_scene_multiple_outlined', { values: { count: wholeScene.otherOutlines.length + 1 }, default: 'Whole scene, {count, plural, one {# crop region outlined} other {# crop regions outlined}}' })
                                        : wholeScene.pinned
                                            ? $_('detection.whole_scene_chip_pinned', { default: 'Whole scene, the crop is outlined' })
                                            : $_('detection.whole_scene_chip', { default: 'Whole scene' })}
                                </span>
                            {/if}
                        {/if}
                    </div>
                        <div
                            class="relative flex shrink-0 flex-col bg-media"
                            data-detection-media-footer
                        >
                            {#if mediaFooterHasActions}
                            <!-- The star and play buttons sit on the photograph's lower edge rather than in a black
                                 band of their own under it, so the identification starts a band higher. -->
                            <div class="flex flex-col gap-3 px-4 {canUseWholeScene ? 'pt-3' : ''}">
                                {#if canUseWholeScene}
                                    <div class="flex" data-detection-whole-scene-actions>
                                        <button
                                            type="button"
                                            class="btn btn-primary btn-focus-on-dark min-h-11 gap-2 px-4 text-sm max-sm:grow"
                                            disabled={snapshotApplyPending || snapshotGeneratePending}
                                            onclick={(event) => { event.stopPropagation(); void useWholeSceneAsPhotograph(); }}
                                        >
                                            {#if snapshotApplyPending}
                                                <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true"></span>
                                            {/if}
                                            {$_('detection.whole_scene_use', { default: 'Use the whole scene as the photograph' })}
                                        </button>
                                    </div>
                                {/if}

                                <div class="pointer-events-none absolute inset-x-4 bottom-full z-30 mb-3 flex flex-wrap items-center gap-2" data-detection-media-actions>
                                        {#if canShowFavoriteAction}
                                            <button
                                                type="button"
                                                onclick={handleFavoriteToggle}
                                                disabled={favoritePending}
                                                class="pointer-events-auto inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border shadow-lg backdrop-blur-xs transition-colors disabled:opacity-60 focus-ring-on-dark {detection.is_favorite ? 'border-on-media-accent bg-accent text-accent-fg hover:bg-accent-hover' : 'border-on-media/35 bg-media/45 text-on-media hover:bg-media/60'}"
                                                title={detection.is_favorite ? $_('detection.favorite_remove', { default: 'Remove favourite' }) : $_('detection.favorite_add', { default: 'Add favourite' })}
                                                aria-label={detection.is_favorite ? $_('detection.favorite_remove', { default: 'Remove favourite' }) : $_('detection.favorite_add', { default: 'Add favourite' })}
                                            >
                                                {#if favoritePending}
                                                    <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
                                                {:else}
                                                    <svg class="h-4 w-4" viewBox="0 0 24 24" fill={detection.is_favorite ? 'currentColor' : 'none'} stroke="currentColor" stroke-width="1.8">
                                                        <path stroke-linecap="round" stroke-linejoin="round" d="M11.05 2.927c.3-.921 1.603-.921 1.902 0l2.02 6.217a1 1 0 00.95.69h6.54c.969 0 1.371 1.24.588 1.81l-5.29 3.844a1 1 0 00-.364 1.118l2.02 6.217c.3.921-.755 1.688-1.539 1.118l-5.29-3.844a1 1 0 00-1.175 0l-5.29 3.844c-.783.57-1.838-.197-1.539-1.118l2.02-6.217a1 1 0 00-.364-1.118L.98 11.644c-.783-.57-.38-1.81.588-1.81h6.54a1 1 0 00.95-.69l2.02-6.217z" />
                                                    </svg>
                                                {/if}
                                            </button>
                                        {/if}
                                        {#if canPlayVideo}
                                            <button
                                                type="button"
                                                onclick={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                    onPlayVideo?.(detection.frigate_event, 'user');
                                                }}
                                                onpointerdown={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                }}
                                                ontouchstart={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                }}
                                                title={fullVisitFetched ? $_('video_player.full_visit_ready', { default: 'Full visit clip ready' }) : $_('detection.play_video', { values: { species: primaryName } })}
                                                aria-label={fullVisitFetched ? $_('detection.play_full_visit', { values: { species: primaryName }, default: 'Play full visit clip of {species}' }) : $_('detection.play_video', { values: { species: primaryName } })}
                                                class="pointer-events-auto inline-flex h-11 min-w-11 items-center justify-center rounded-full border shadow-xl backdrop-blur-xs transition-colors duration-150 focus:outline-hidden focus:ring-2 focus:ring-focus-on-dark {fullVisitFetched ? 'gap-2 border-on-media-accent/30 bg-accent px-3 text-accent-fg hover:bg-accent-hover' : 'w-11 border-on-media/25 bg-media/55 text-on-media'}"
                                            >
                                                <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                                    <path d="M8 5v14l11-7z"/>
                                                </svg>
                                                {#if fullVisitFetched}
                                                    <span class="text-2xs font-semibold">{$_('video_player.full_visit_action', { default: 'Full visit' })}</span>
                                                {/if}
                                            </button>
                                        {/if}
                                        {#if isManualObservation}
                                            <div class="inline-flex min-h-11 items-center gap-2 rounded-full border border-on-media/25 bg-media/55 px-3.5 text-xs font-semibold text-on-media shadow-xl backdrop-blur-xs">
                                                <svg class="h-4 w-4 text-on-media-accent" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 16V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>
                                                {$_('detection.uploaded', { default: 'Uploaded' })}
                                            </div>
                                        {/if}
                                        {#if showFetchFullVisitAction}
                                            <button
                                                type="button"
                                                onclick={handleFetchFullVisitClick}
                                                onpointerdown={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                }}
                                                ontouchstart={(e) => {
                                                    e.preventDefault();
                                                    e.stopPropagation();
                                                }}
                                                disabled={fullVisitFetchState === 'fetching'}
                                                aria-label={fullVisitFetchLabel}
                                                class="pointer-events-auto inline-flex min-h-11 items-center gap-2 rounded-full border border-on-media/25 bg-media/55 px-4 py-2 text-2xs font-semibold text-on-media shadow-xl backdrop-blur-xs transition-colors duration-150 hover:bg-accent-hover disabled:cursor-wait disabled:opacity-75 focus:outline-hidden focus:ring-2 focus:ring-focus-on-dark"
                                            >
                                                {#if fullVisitFetchState === 'fetching'}
                                                    <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent"></span>
                                                {:else}
                                                    <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                                                        <path d="M10 3v8"></path>
                                                        <path d="M7 8l3 3 3-3"></path>
                                                        <path d="M4 14h12"></path>
                                                    </svg>
                                                {/if}
                                                <span>{fullVisitFetchLabel}</span>
                                            </button>
                                        {/if}
                                        {#if frigateIssueBadgeVisible}
                                            <div
                                                class="inline-flex h-11 w-11 items-center justify-center rounded-full border border-on-media-fail/70 bg-media/55 text-on-media-fail shadow-lg backdrop-blur-xs"
                                                title={videoFailureInsight.summary}
                                                aria-label={videoFailureInsight.summary}
                                                role="img"
                                            >
                                                <img src={FRIGATE_LOGO_URL} alt="" aria-hidden="true" class="h-4 w-4 rounded-[3px] bg-on-media/95 p-0.5 object-contain" />
                                            </div>
                                        {/if}
                                        {#if wholeScene.pinned && wholeSceneReady}
                                            <!-- The way back sits on the photograph it changes, at the end of its row of controls. -->
                                            <button
                                                type="button"
                                                class="btn btn-focus-on-dark photo-chip pointer-events-auto ml-auto min-h-11 border border-on-media/25 px-3 text-xs shadow-lg"
                                                onclick={(event) => { event.stopPropagation(); resetMediaView(); }}
                                                data-detection-whole-scene-back
                                            >
                                                {$_('detection.whole_scene_back', { default: 'Back to the crop' })}
                                            </button>
                                        {/if}
                                </div>
                            </div>
                            {/if}

                            {#if !recordStacked && showInlineFramePicker}<div class="pt-3" data-detection-footer-strip>{@render visitStrip()}</div>{/if}
                        </div>
                </div>

                {#if !recordShortLandscape.current}{@render decision()}{/if}
            </div>

            <!-- Reference for the species and the record, and the identifiers last. Held sideways on a
                 phone this column also holds the decision, above the reference. -->
            <div data-detection-details-column class="flex min-w-0 flex-1 flex-col gap-5 wrap-break-word px-5 pb-5 sm:px-6 sm:pb-6 {recordHasReference ? 'lg:overflow-y-auto lg:pt-6' : 'lg:px-4 lg:pb-4'} sm:max-lg:short:overflow-y-auto sm:max-lg:short:pt-6">
            {#if recordShortLandscape.current}{@render decision()}{/if}
            <div class="flex min-w-0 flex-col gap-5 {showTagDropdown ? 'blur-xs pointer-events-none select-none' : ''}" data-detection-secondary-column>
            {#if !isUnknownSpecies && detection.scientific_name}
                <TaxonomyLineage scientificName={detection.scientific_name} commonName={detection.common_name} />
            {/if}

            {#if !isUnknownSpecies && detection.display_name}
                <RecordSpeciesReference speciesName={detection.display_name} scientificName={detection.scientific_name} {primaryName} unitSystem={weatherUnitSystem} bind:info={speciesInfo} />
            {/if}

            {#if canShowInat && inatConnectedUser}
                {#key detection.frigate_event}
                    <RecordInaturalist eventId={detection.frigate_event} connectedUser={inatConnectedUser} />
                {/key}
            {/if}

            <!-- One panel per identification: a new species starts its AI note afresh. -->
            {#key recordClassificationKey(detection)}
                <RecordAiAnalysis {detection} {llmReady} {readOnly} />
            {/key}

            <!-- The identifiers, last on screen and last in the tab order. -->
            <RecordTechnicalDetails title={$_('detection.id')} identifier={detection.frigate_event} data-detection-technical-identity>
                    {#if frigateEventUrl}
                        <p class="mt-1">
                            <a
                                href={frigateEventUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                class="inline-flex min-h-6 items-center rounded-sm font-semibold text-accent-ink underline underline-offset-2 hover:text-accent-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus"
                                data-frigate-event-link
                            >
                                {$_('detection.open_in_frigate', { default: 'Open in Frigate' })} &nearr;
                            </a>
                        </p>
                    {:else if hasOwnerDetectionActions && !isManualObservation && missingEventMetadataGone}
                        <p class="mt-1 text-muted" data-frigate-event-gone>
                            {$_('detection.open_in_frigate_gone', { default: 'No longer in Frigate' })}
                        </p>
                    {/if}
                    {#if hasOwnerDetectionActions && !isManualObservation}
                        <RangeFallbackNote eventId={detection.frigate_event} />
                    {/if}
            </RecordTechnicalDetails>
            </div>
        </div>
        </div>

        {#if hasOwnerDetectionActions && showTagDropdown}
            <div
                data-manual-tag-dialog
                class="absolute left-0 right-0 top-0 z-50 flex h-full items-center justify-center overscroll-contain bg-media/40 p-4 backdrop-blur-xs"
                style={manualTagViewportStyle}
                onclick={(e) => {
                    if (e.target === e.currentTarget && !updatingTag) {
                        showTagDropdown = false;
                    }
                }}
                onkeydown={(e) => {
                    if (e.key === 'Escape' && !updatingTag) {
                        e.preventDefault();
                        e.stopPropagation();
                        showTagDropdown = false;
                    }
                }}
                role="dialog"
                aria-modal="true"
                aria-labelledby="manual-tag-dialog-title"
                tabindex="-1"
            >
                <div
                    class="mx-2 flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl animate-in fade-in zoom-in-95 touch-pan-y"
                    aria-busy={updatingTag}
                >
                    <div class="flex shrink-0 items-center justify-between border-b border-line-soft px-5 py-2 ">
                        <h4 id="manual-tag-dialog-title" class="text-sm font-bold text-strong">
                            {$_('actions.pick_species')}
                        </h4>
                        <button
                            type="button"
                            onclick={() => showTagDropdown = false}
                            disabled={updatingTag}
                            class="btn btn-ghost min-h-11 px-3 text-xs"
                        >
                            {$_('common.cancel')}
                        </button>
                    </div>
                    <div class="shrink-0 border-b border-line-soft bg-surface-raised p-4 ">
                        <label for="manual-tag-species-search" class="sr-only">
                            {$_('detection.tagging.search_placeholder')}
                        </label>
                        <input
                            id="manual-tag-species-search"
                            type="text"
                            bind:value={tagSearchQuery}
                            disabled={updatingTag}
                            autocomplete="off"
                            enterkeyhint="search"
                            placeholder={$_('detection.tagging.search_placeholder')}
                            class="input-base min-h-11 text-base sm:text-sm"
                        />
                    </div>
                    <div class="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
                        {#each searchResults as result}
                            {@const names = speciesPickerNames(result)}
                            {@const isPending = updatingTag && pendingManualTagId === result.id}
                            <button
                                type="button"
                                onclick={() => handleManualTag(result)}
                                disabled={updatingTag}
                                class="min-h-11 w-full rounded-lg px-4 py-2.5 text-left text-sm font-medium transition-all touch-manipulation hover:bg-accent-soft hover:text-accent-ink disabled:cursor-wait disabled:opacity-60 {result.id === detection.display_name ? 'bg-accent-soft text-accent-ink font-bold' : 'text-muted'}"
                            >
                                <span class="block text-sm leading-tight">
                                    {names.primary}
                                    {#if isPending}
                                        <span class="ml-2 inline-flex items-center gap-1 text-3xs text-accent-ink">
                                            <span class="inline-block h-2 w-2 rounded-full border border-current border-t-transparent animate-spin"></span>
                                            {$_('common.saving')}
                                        </span>
                                    {/if}
                                </span>
                                {#if names.secondary}
                                    <span class="block text-2xs text-muted italic">{names.secondary}</span>
                                {/if}
                            </button>
                        {/each}
                        {#if searchResults.length === 0}
                            <p class="px-4 py-6 text-sm text-muted italic text-center">
                                {isSearching ? $_('common.loading') : $_('detection.tagging.no_results')}
                            </p>
                        {/if}
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
