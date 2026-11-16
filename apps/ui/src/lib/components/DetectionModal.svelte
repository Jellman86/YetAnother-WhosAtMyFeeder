<script lang="ts">
    import { compassPointKey, weatherConditionMessage } from '../utils/weather-condition';
    import DialogCloseButton from './DialogCloseButton.svelte';
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
        analyzeDetection,
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
        createInaturalistDraft,
        submitInaturalistObservation,
        fetchSpeciesInfo,
        fetchCommonNameOverride,
        setCommonNameOverride,
        clearCommonNameOverride,
        fetchEbirdNearby,
        fetchDetectionConversation,
        sendDetectionConversationMessage,
        type SearchResult,
        type AudioContextDetection,
        type InaturalistDraft,
        type SpeciesInfo,
        type EbirdNearbyResult,
        type ConversationTurn,
        type SnapshotStatusResponse,
        type SnapshotCandidate,
        type BirdObservation
    } from '../api';
    import type { Detection } from '../api';
    import { withAuthParams } from '../api/core';
    import { appApiPath } from '../app/url-base';
    import ReclassificationOverlay from './ReclassificationOverlay.svelte';
    import FrameStrip from './FrameStrip.svelte';
    import CountedBirds from './CountedBirds.svelte';
    import BirdScanControl from './BirdScanControl.svelte';
    import MediaImage from './MediaImage.svelte';
    import MarkdownText from './MarkdownText.svelte';
    import { currentMoment, groupCandidatesIntoMoments, preferredCandidate, type FrameMoment } from '../utils/frame-moments';
    import { WholeScenePeek } from '../utils/whole-scene-peek.svelte';
    import { photoFitFor, type PhotoFit } from '../utils/photo-fit';
    import { speciesPickerNames } from '../utils/species-picker';
    import { detectionsStore, type ReclassificationProgress } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { classifierLabelsStore } from '../stores/classifier_labels.svelte';
    import { toastStore } from '../stores/toast.svelte';
    import { confirmAction } from '../stores/confirm_dialog.svelte';
    import { birdNames } from '../naming';
    import { _ } from 'svelte-i18n';
    import { get } from 'svelte/store';
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
        formatDistance,
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
            return $_('detection.video_analysis.fallback_desc', { default: 'Video analysis was unavailable, so this detection was classified from a single frame. Confidence may be lower.' });
        }
        return $_('detection.video_analysis.verified_desc');
    });
    let hideActionLabel = $derived(
        detection.is_hidden
            ? $_('actions.unhide_detection', { default: 'Unhide detection' })
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
    let analyzingAI = $state(false);
    let audioContextOpen = $state(false);
    let audioContextLoading = $state(false);
    let audioContextLoaded = $state(false);
    let audioContext = $state<AudioContextDetection[]>([]);
    let audioContextSuppressed = $state(0);
    let audioContextError = $state<string | null>(null);
    let inatPanelOpen = $state(false);
    let inatLoading = $state(false);
    let inatSubmitting = $state(false);
    let inatError = $state<string | null>(null);
    let inatDraft = $state<InaturalistDraft | null>(null);
    let inatNotes = $state('');
    let inatLat = $state<number | null>(null);
    let inatLon = $state<number | null>(null);
    let inatPlace = $state('');
    // Enrichment state
    let speciesInfo = $state<SpeciesInfo | null>(null);
    let speciesInfoLoading = $state(false);
    let speciesInfoError = $state<string | null>(null);
    let failedSpeciesReferenceUrl = $state<string | null>(null);
    let ebirdNearby = $state<EbirdNearbyResult | null>(null);
    let ebirdNearbyLoading = $state(false);
    let ebirdNearbyError = $state<string | null>(null);
    let lastEnrichmentKey = $state<string | null>(null);
    let commonNameEditorOpen = $state(false);
    let moreActionsOpen = $state(false);
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
        const parentIdentity = untrack(() => countedParentIdentity);
        const isCurrent = () => requestEpoch === snapshotControlsEpoch
            && detection?.frigate_event === eventId && hasOwnerDetectionActions;
        if (!isCurrent()) return;
        snapshotCandidatesLoading = true;
        snapshotCandidatesError = false;
        try {
            const [status, candidateList] = await Promise.all([
                fetchSnapshotStatus(eventId),
                fetchSnapshotCandidates(eventId)
            ]);
            if (!isCurrent()) return;
            snapshotStatus = status;
            snapshotCandidates = candidateList.candidates ?? [];
            if (parentIdentity === countedParentIdentity) {
                countedBirds = candidateList.birds ?? [];
                countedBirdsGeneration += 1;
                countedBirdsError = false;
                countedBirdsLoading = false;
            }
            currentSnapshotCandidateId = candidateList.current_candidate_id ?? null;
            currentSnapshotSource = candidateList.current_source ?? status.source ?? null;
        } catch {
            if (!isCurrent()) return;
            snapshotStatus = null;
            snapshotCandidates = [];
            if (parentIdentity === countedParentIdentity) {
                countedBirds = [];
                countedBirdsGeneration += 1;
                countedBirdsLoading = false;
            }
            snapshotCandidatesError = true;
            currentSnapshotCandidateId = null;
            currentSnapshotSource = null;
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
            countedBirds = [];
            snapshotCandidatesLoading = false;
            currentSnapshotCandidateId = null;
            currentSnapshotSource = null;
            return;
        }

        if (snapshotControlsSubject !== eventId) {
            snapshotControlsSubject = eventId;
            snapshotCandidates = [];
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

    let aiAnalysis = $state<string | null>(null);
    let conversationTurns = $state<ConversationTurn[]>([]);
    let conversationInput = $state('');
    let conversationLoading = $state(false);
    let conversationSending = $state(false);
    let conversationError = $state<string | null>(null);
    let lastEventId = $state<string | null>(null);
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
    let snapshotApplyPending = $state(false);
    let snapshotGeneratePending = $state(false);
    let currentSnapshotCandidateId = $state<string | null>(null);
    let currentSnapshotSource = $state<string | null>(null);
    /** The strip moment being saved as the photograph, while the request is in flight. */
    let applyingMomentKey = $state<string | null>(null);
    let snapshotRefreshToken = $state(Date.now());
    const settledMediaVersion = $derived(
        detectionsStore.settledMediaVersion(detection.frigate_event)
    );
    const snapshotCacheToken = $derived(`${snapshotRefreshToken}.${settledMediaVersion}`);
    let tagSearchQuery = $state('');
    let searchResults = $state<SearchResult[]>([]);
    let isSearching = $state(false);
    let videoErrorDetailsOpen = $state(false);
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
    // Spectrogram <img> and audio clip cannot send auth headers, so append the
    // JWT as a query param (mirrors Frigate media URLs) to avoid 401s when
    // authentication is enabled.
    const matchedSpectrogramUrl = $derived(
        matchedAudioEntry?.birdnet_id != null
            ? withAuthParams(`${appApiPath(`/audio/spectrogram/${matchedAudioEntry.birdnet_id}`)}?width=600`)
            : null
    );
    // The spectrogram address that failed to load, so its box shows the quiet placeholder until the
    // record moves to another call.
    let failedSpectrogramUrl = $state<string | null>(null);
    const matchedAudioClipUrl = $derived(
        matchedAudioEntry?.birdnet_id != null
            ? withAuthParams(appApiPath(`/audio/clip/${matchedAudioEntry.birdnet_id}`))
            : null
    );
    // Playback state bound to the hidden <audio> element. Reset whenever
    // the modal switches detections so the cursor + button state don't
    // carry over.
    let audioCurrentTime = $state(0);
    let audioDuration = $state(0);
    let audioPaused = $state(true);
    let audioElement = $state<HTMLAudioElement | null>(null);
    const audioProgressPct = $derived(
        audioDuration > 0 ? Math.min(100, Math.max(0, (audioCurrentTime / audioDuration) * 100)) : 0
    );
    function formatAudioClipTime(seconds: number): string {
        if (!isFinite(seconds) || seconds < 0) return '0:00';
        const total = Math.floor(seconds);
        return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
    }
    $effect(() => {
        detection.frigate_event;
        untrack(() => {
            audioCurrentTime = 0;
            audioDuration = 0;
            audioPaused = true;
            // If the previous detection's clip was playing, stop it.
            if (audioElement && !audioElement.paused) {
                try { audioElement.pause(); } catch { /* noop */ }
            }
        });
    });
    function toggleAudioPlayback() {
        if (!audioElement) return;
        if (audioElement.paused) {
            audioElement.play().catch(() => {});
        } else {
            audioElement.pause();
        }
    }
    function seekAudioFromSpectrogramClick(event: MouseEvent) {
        if (!audioElement || !audioElement.duration || !isFinite(audioElement.duration)) return;
        const target = event.currentTarget as HTMLElement;
        const img = target.querySelector('img');
        if (!img) return;
        const rect = img.getBoundingClientRect();
        if (rect.width <= 0) return;
        const fraction = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
        audioElement.currentTime = fraction * audioElement.duration;
        if (audioElement.paused) audioElement.play().catch(() => {});
    }

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
                audioContextOpen = false;
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
            audioContextOpen = false;
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
    const originalFrigateSnapshotAvailable = $derived(snapshotStatus?.original_frigate_snapshot_available === true);
    const fullFrameSnapshotCandidate = $derived(
        findMatchingFullFrameCandidate(snapshotCandidates, currentSnapshotCandidateId)
    );
    const scanFrameCandidate = $derived(findScanFrameCandidate(snapshotCandidates, currentSnapshotCandidateId, currentSnapshotSource));
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
        return () => window.removeEventListener('resize', measureWholeScene);
    });
    onDestroy(wholeScene.destroy);
    const canGenerateSnapshotCandidates = $derived(
        !snapshotApplyPending
        && !snapshotGeneratePending
        && Boolean(snapshotStatus?.high_quality_bird_crop_enabled)
    );
    const showInlineFramePicker = $derived(
        hasOwnerDetectionActions
        && hasFrameSource
        && !reclassifyProgress
        && (
            snapshotCandidatesLoading
            || frameMoments.length > 0
            || canGenerateSnapshotCandidates
        )
    );

    const UNKNOWN_SPECIES_LABELS = new Set(['unknown', 'unknown bird', 'background']);
    const isUnknownSpecies = $derived(UNKNOWN_SPECIES_LABELS.has((detection.display_name || '').trim().toLowerCase()));

    const enrichmentModeSetting = $derived(settingsStore.settings?.enrichment_mode ?? authStore.enrichmentMode ?? 'per_enrichment');
    const enrichmentSingleProviderSetting = $derived(settingsStore.settings?.enrichment_single_provider ?? authStore.enrichmentSingleProvider ?? 'wikipedia');
    const enrichmentSummaryProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_summary_source ?? authStore.enrichmentSummarySource ?? 'wikipedia')
    );
    const enrichmentSightingsProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_sightings_source ?? authStore.enrichmentSightingsSource ?? 'disabled')
    );
    const enrichmentSeasonalityProvider = $derived(
        enrichmentModeSetting === 'single'
            ? enrichmentSingleProviderSetting
            : (settingsStore.settings?.enrichment_seasonality_source ?? authStore.enrichmentSeasonalitySource ?? 'disabled')
    );
    const enrichmentLinksProviders = $derived(
        enrichmentModeSetting === 'single'
            ? [enrichmentSingleProviderSetting]
            : (settingsStore.settings?.enrichment_links_sources ?? authStore.enrichmentLinksSources ?? ['wikipedia', 'inaturalist'])
    );
    const enrichmentLinksProvidersNormalized = $derived(
        enrichmentLinksProviders.map((provider) => String(provider || '').toLowerCase())
    );
    const ebirdEnabled = $derived(settingsStore.settings?.ebird_enabled ?? authStore.ebirdEnabled ?? false);
    const ebirdRadius = $derived(
        settingsStore.settings?.ebird_default_radius_km ?? authStore.ebirdDefaultRadiusKm ?? 25
    );
    const ebirdDaysBack = $derived(
        settingsStore.settings?.ebird_default_days_back ?? publicSettingsStore.settings?.ebird_default_days_back ?? 14
    );
    const showEbirdNearby = $derived(
        enrichmentSightingsProvider === 'ebird' || enrichmentSeasonalityProvider === 'ebird'
    );
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
    const videoClassificationSources = $derived(
        Object.entries(videoClassificationDiagnostics?.sources ?? {})
    );
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
    const videoStatusNoticeTone = $derived.by(() => {
        const status = (detection.video_classification_status || '').trim().toLowerCase();
        // "rose" reserved for the genuinely-stuck cases where there's no
        // recovered classification to fall back on.  When the snapshot path
        // already produced a real result we tier attention/slate based on
        // confidence so we don't over-alarm successful classifications.
        if (status === 'failed' && !videoAnalysisAbstained && currentClassificationSource !== 'snapshot') {
            return {
                kind: 'rose' as const,
                container: 'bg-rose-50/80 dark:bg-rose-500/10 border-rose-200/80 dark:border-rose-500/30 text-rose-900 dark:text-rose-200',
                detailsContainer: 'border-rose-200/70 dark:border-rose-400/25',
                detailsSummary: 'text-rose-700 dark:text-rose-300',
            };
        }
        const score = Number(detection.score ?? 0);
        if (score >= 0.8) {
            return {
                kind: 'slate' as const,
                container: 'bg-slate-50/80 dark:bg-slate-800/40 border-slate-200/80 dark:border-slate-700/60 text-slate-700 dark:text-slate-300',
                detailsContainer: 'border-slate-200/70 dark:border-slate-700/60',
                detailsSummary: 'text-slate-700 dark:text-slate-300',
            };
        }
        return {
            kind: 'attention' as const,
            container: 'bg-attention-50/80 dark:bg-attention-500/10 border-attention-200/80 dark:border-attention-500/30 text-attention-900 dark:text-attention-200',
            detailsContainer: 'border-attention-200/70 dark:border-attention-500/30',
            detailsSummary: 'text-attention-700 dark:text-attention-300',
        };
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
            return $_(
                `detection.reclassification.snapshot_fallback_reason.${error}`,
                { default: $_('detection.video_analysis.fallback_desc', { default: 'Video analysis was unavailable, so this detection was classified from a single frame. Confidence may be lower.' }) }
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

    function videoEvidenceSourceLabel(source: string): string {
        if (source === 'full_frame') {
            return $_('detection.video_analysis.evidence.full_frame', { default: 'Full frame' });
        }
        if (source === 'frigate_hint_crop') {
            return $_('detection.video_analysis.evidence.frigate_hint_crop', { default: 'Frigate-guided crop' });
        }
        if (source === 'frigate_region_crop') {
            return $_('detection.video_analysis.evidence.frigate_region_crop', { default: 'Frigate-tracked area' });
        }
        if (source === 'model_crop') {
            return $_('detection.video_analysis.evidence.model_crop', { default: 'AI crop' });
        }
        return source.replaceAll('_', ' ');
    }

    function formatEbirdDate(dateStr?: string | null) {
        if (!dateStr) return '—';
        return formatDateTime(dateStr);
    }

    $effect(() => {
        if (!detection?.frigate_event) return;
        if (detection.frigate_event !== lastEventId) {
            lastEventId = detection.frigate_event;
            videoErrorDetailsOpen = false;
            aiAnalysis = llmReady ? (detection.ai_analysis || null) : null;
            inatPanelOpen = false;
            inatDraft = null;
            inatNotes = '';
            inatLat = null;
            inatLon = null;
            inatPlace = '';
            conversationTurns = [];
            conversationInput = '';
            conversationError = null;
            if (aiAnalysis && llmReady && authStore.canViewAiConversation) {
                loadConversation();
            }
        }
    });

    $effect(() => {
        if (!llmReady) {
            aiAnalysis = null;
            conversationTurns = [];
            conversationInput = '';
            conversationError = null;
        }
    });

    async function loadSpeciesInfo(speciesName: string) {
        speciesInfoLoading = true;
        speciesInfoError = null;
        try {
            speciesInfo = await fetchSpeciesInfo(speciesName);
        } catch (e) {
            speciesInfoError = getErrorMessage(e) || 'Failed to load species info';
        } finally {
            speciesInfoLoading = false;
        }
    }

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

    async function loadEbirdNearby(speciesName: string, scientificName?: string) {
        ebirdNearbyLoading = true;
        ebirdNearbyError = null;
        try {
            const res = await fetchEbirdNearby(speciesName, scientificName);
            if (res.status === 'error') {
                ebirdNearbyError = res.message || 'Failed to load eBird sightings';
                ebirdNearby = null;
            } else {
                ebirdNearby = res;
            }
        } catch (e) {
            ebirdNearbyError = getErrorMessage(e) || 'Failed to load eBird sightings';
        } finally {
            ebirdNearbyLoading = false;
        }
    }

    async function loadConversation() {
        if (!llmReady || !aiAnalysis || !authStore.canViewAiConversation) return;
        conversationLoading = true;
        conversationError = null;
        try {
            conversationTurns = await fetchDetectionConversation(detection.frigate_event);
        } catch (e) {
            conversationError = getErrorMessage(e) || $_('detection.ai.conversation_error');
        } finally {
            conversationLoading = false;
        }
    }

    async function sendConversation() {
        const message = conversationInput.trim();
        if (!message || conversationSending) return;
        conversationSending = true;
        conversationError = null;
        try {
            conversationTurns = await sendDetectionConversationMessage(detection.frigate_event, message);
            conversationInput = '';
        } catch (e) {
            conversationError = getErrorMessage(e) || $_('detection.ai.conversation_error');
        } finally {
            conversationSending = false;
        }
    }

    $effect(() => {
        if (!detection?.display_name || isUnknownSpecies) return;
        const enrichmentKey = [
            detection.display_name,
            enrichmentSummaryProvider,
            enrichmentSightingsProvider,
            enrichmentSeasonalityProvider,
            ebirdEnabled,
            ebirdRadius,
            ebirdDaysBack
        ].join('|');
        if (enrichmentKey === lastEnrichmentKey) return;
        lastEnrichmentKey = enrichmentKey;

        speciesInfo = null;
        speciesInfoError = null;
        ebirdNearby = null;
        ebirdNearbyError = null;

        if (enrichmentSummaryProvider !== 'disabled') {
            void loadSpeciesInfo(detection.display_name);
        }

        const needsEbirdNearby = ebirdEnabled && showEbirdNearby;
        if (needsEbirdNearby) {
            void loadEbirdNearby(detection.display_name, detection.scientific_name ?? undefined);
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
            const defaults = settingsStore.settings;
            inatLat = inatDraft.latitude ?? defaults?.inaturalist_default_latitude ?? defaults?.location_latitude ?? null;
            inatLon = inatDraft.longitude ?? defaults?.inaturalist_default_longitude ?? defaults?.location_longitude ?? null;
            inatPlace = inatDraft.place_guess ?? defaults?.inaturalist_default_place_guess ?? '';
        } catch (e) {
            inatError = getErrorMessage(e) || 'Failed to load iNaturalist draft';
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
        } catch (e) {
            inatError = getErrorMessage(e) || 'Failed to submit to iNaturalist';
        } finally {
            inatSubmitting = false;
        }
    }

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
                [$_('detection.weather_wind'), speed, formatWindDirection(detection.weather_wind_direction)]
                    .filter(Boolean)
                    .join(' ')
            );
        }
        if (detection.weather_cloud_cover !== undefined && detection.weather_cloud_cover !== null) {
            parts.push(`${$_('detection.weather_cloud')} ${Math.round(detection.weather_cloud_cover)}%`);
        }
        if (detection.weather_rain !== undefined && detection.weather_rain !== null && detection.weather_rain > 0) {
            parts.push(`${$_('detection.weather_rain')} ${formatPrecip(detection.weather_rain)}`);
        }
        if (detection.weather_snowfall !== undefined && detection.weather_snowfall !== null && detection.weather_snowfall > 0) {
            parts.push(`${$_('detection.weather_snow')} ${formatPrecip(detection.weather_snowfall)}`);
        }
        // Measured by a light sensor at the detection (#945); never estimated from the weather.
        const light = formatIlluminance(detection.illuminance_lux);
        if (light !== null) {
            parts.push(`${$_('detection.weather_light', { default: 'Light' })} ${light}`);
        }
        return parts.join(' · ');
    });
    const ebirdRadiusLabel = $derived(
        formatDistance(ebirdRadius, weatherUnitSystem, {
            metric: $_('common.unit_km', { default: 'km' }),
            imperial: $_('common.unit_mi', { default: 'mi' })
        })
    );

    function formatAudioOffset(offsetSeconds: number): string {
        const abs = Math.abs(offsetSeconds);
        const mins = Math.floor(abs / 60);
        const secs = abs % 60;
        const label = mins > 0 ? `${mins}m` : `${secs}s`;
        if (offsetSeconds === 0) return '0s';
        return `${offsetSeconds > 0 ? '+' : '-'}${label}`;
    }

    function toggleAudioContext(event: MouseEvent) {
        event.stopPropagation();
        audioContextOpen = !audioContextOpen;
    }

    async function handleAIAnalysis(force: boolean = false) {
        if (readOnly) return;
        if (!detection) return;
        if (!llmReady) return;
        analyzingAI = true;
        if (force) {
            aiAnalysis = null; // Clear existing analysis when forcing regeneration
            // Reset the conversation thread so the UI reflects the new analysis context.
            conversationTurns = [];
            conversationInput = '';
            conversationError = null;
            conversationLoading = false;
            conversationSending = false;
        }

        try {
            const result = await analyzeDetection(detection.frigate_event, force);
            aiAnalysis = result.analysis;
            detection.ai_analysis = result.analysis;
            detection.ai_analysis_timestamp = result.analysis_timestamp;
            detectionsStore.updateDetection({
                ...detection,
                ai_analysis: result.analysis,
                ai_analysis_timestamp: result.analysis_timestamp,
            });
            await loadConversation();
        } catch (e) {
            aiAnalysis = $_('detection.ai.error', { values: { message: getErrorMessage(e) || 'Analysis failed' } });
        } finally {
            analyzingAI = false;
        }
    }

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
            aiAnalysis = nextDetection.ai_analysis ?? null;
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
            toastStore.error($_('detection.move_to_garden_failed', { default: 'Could not move this record to Garden: {message}', values: { message: getErrorMessage(e) } }));
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
                toastStore.success($_('detection.favorite_removed', { default: 'Removed from favorites' }));
            } else {
                const result = await favoriteDetection(detection.frigate_event);
                detection.is_favorite = true;
                detection.archive_state = asArchiveState(result.archive_state) ?? 'pending';
                detectionsStore.updateDetection({ ...detection, is_favorite: true, archive_state: detection.archive_state });
                toastStore.success($_('detection.favorite_added', { default: 'Added to favorites' }));
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

    /** "Use this frame" from the strip: the photograph changes, the identification does not. */
    async function removePhotoChoice(candidateId: string, dismissed: boolean): Promise<void> {
        if (!hasOwnerDetectionActions || snapshotApplyPending) return;
        const eventId = detection.frigate_event;
        snapshotApplyPending = true;
        try {
            const response = await dismissSnapshotCandidate(eventId, candidateId, dismissed);
            if (detection.frigate_event === eventId && hasOwnerDetectionActions) snapshotCandidates = response.candidates;
        } catch (error) {
            toastStore.error(getErrorMessage(error));
            throw error;
        } finally {
            if (detection.frigate_event === eventId) snapshotApplyPending = false;
        }
    }

    async function handleUseMoment(moment: FrameMoment) {
        if (!hasOwnerDetectionActions || snapshotApplyPending) return;
        applyingMomentKey = moment.key;
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
            applyingMomentKey = null;
        }
    }

    async function handleApplySnapshot(
        mode: 'candidate' | 'revert_original',
        candidateId?: string | null
    ) {
        if (!authStore.hasOwnerAccess || readOnly || !detection || snapshotApplyPending) return;
        snapshotApplyPending = true;
        try {
            const result = await applySnapshotCandidate(detection.frigate_event, {
                mode,
                candidate_id: candidateId ?? null
            });
            snapshotStatus = result;
            snapshotRefreshToken = Date.now();
            currentSnapshotSource = result.source ?? null;
            currentSnapshotCandidateId = result.applied_candidate_id ?? null;
            resetMediaView();
            toastStore.success($_('detection.snapshot_apply_success', { default: 'Snapshot updated' }));
            await refreshSnapshotControls(detection.frigate_event);
        } catch (e) {
            toastStore.error(getErrorMessage(e) || $_('common.error', { default: 'Action failed' }));
        } finally {
            snapshotApplyPending = false;
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
        const eventId = detection.frigate_event;
        snapshotGeneratePending = true;
        try {
            const result = await generateHighQualityBirdCropSnapshot(eventId);
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
            toastStore.error(getErrorMessage(e) || $_('common.error', { default: 'Action failed' }));
        } finally {
            snapshotGeneratePending = false;
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

<style>
    .ai-surface {
        position: relative;
        overflow: hidden;
        padding: 1.25rem;
        border-radius: 1.25rem;
        background: rgb(var(--brand-500) / 0.08);
        border: 1px solid rgb(var(--brand-500) / 0.22);
        color: rgb(var(--ai-ink));
        box-shadow: none;
    }

    .ai-surface::before {
        content: '';
        position: absolute;
        inset: 0;
        pointer-events: none;
        border-radius: inherit;
        background: none;
    }

    .ai-surface > * {
        position: relative;
        z-index: 1;
    }

    :global(.dark) .ai-surface,
    :global([data-theme='dark']) .ai-surface {
        /* Softer dark surface: keep the teal identity, reduce the "hard slab" look. */
        background: rgb(var(--brand-700) / 0.20);
        border-color: rgb(var(--brand-400) / 0.35);
        box-shadow: none;
    }

    .ai-panel {
        position: relative;
    }

    .ai-panel__label {
        font-size: 0.75rem;
        font-weight: 700;
        color: rgb(var(--ai-heading));
        margin-bottom: 0.75rem;
    }

    :global(.ai-markdown-surface) {
        color: inherit;
    }

    :global(.ai-markdown-surface) {
        color: rgb(var(--ai-ink));
    }

    :global(.ai-markdown-surface h1) {
        margin: 0.75rem 0 0.4rem;
        font-size: 1.0rem;
        letter-spacing: 0.02em;
        text-transform: none;
        font-weight: 900;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h2) {
        margin: 0.7rem 0 0.35rem;
        font-size: 0.95rem;
        letter-spacing: 0.015em;
        text-transform: none;
        font-weight: 850;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h3) {
        margin: 0.65rem 0 0.3rem;
        font-size: 0.9rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 800;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h4) {
        margin: 0.6rem 0 0.25rem;
        font-size: 0.86rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 800;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface h5),
    :global(.ai-markdown-surface h6) {
        margin: 0.55rem 0 0.2rem;
        font-size: 0.82rem;
        letter-spacing: 0.01em;
        text-transform: none;
        font-weight: 750;
        color: rgb(var(--ai-heading));
    }

    :global(.ai-markdown-surface p) {
        margin: 0.3rem 0;
        font-size: 0.88rem;
        line-height: 1.55;
        color: inherit;
    }

    :global(.ai-markdown-surface ul) {
        margin: 0.35rem 0 0.65rem;
        padding-left: 1.2rem;
        list-style: disc;
        list-style-position: outside;
    }

    :global(.ai-markdown-surface ol) {
        margin: 0.35rem 0 0.65rem;
        padding-left: 1.3rem;
        list-style: decimal;
        list-style-position: outside;
    }

    :global(.ai-markdown-surface ul ul),
    :global(.ai-markdown-surface ol ol),
    :global(.ai-markdown-surface ul ol),
    :global(.ai-markdown-surface ol ul) {
        margin: 0.2rem 0 0.4rem;
    }

    :global(.ai-markdown-surface li) {
        margin: 0.25rem 0;
        font-size: 0.88rem;
        color: inherit;
    }

    :global(.ai-markdown-surface li::marker) {
        color: rgb(var(--ai-marker) / 0.55);
    }

    :global(.ai-markdown-surface strong) {
        font-weight: 700;
        color: rgb(var(--ai-strong));
    }

    :global(.ai-markdown-surface em) {
        color: rgb(var(--ai-ink) / 0.82);
    }

    :global(.ai-markdown-surface code) {
        font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace;
        font-size: 0.75rem;
        padding: 0.1rem 0.3rem;
        border-radius: 0.4rem;
        background: rgb(var(--brand-700) / 0.1);
        color: rgb(var(--ai-code));
    }

    :global(.dark .ai-markdown-surface code),
    :global([data-theme='dark'] .ai-markdown-surface code) {
        background: rgb(var(--brand-400) / 0.25);
    }

    :global(.ai-markdown-surface pre) {
        margin: 0.5rem 0 0.75rem;
        padding: 0.75rem 0.9rem;
        border-radius: 0.75rem;
        background: rgb(var(--brand-700) / 0.08);
        border: 1px solid rgb(var(--brand-700) / 0.12);
        overflow-x: auto;
    }

    :global(.dark .ai-markdown-surface pre),
    :global([data-theme='dark'] .ai-markdown-surface pre) {
        background: color-mix(in srgb, var(--color-slate-900) 60%, transparent);
        border-color: rgb(var(--brand-400) / 0.2);
    }

    :global(.ai-markdown-surface pre code) {
        display: block;
        padding: 0;
        background: transparent;
        color: inherit;
        font-size: 0.78rem;
        line-height: 1.55;
    }

    :global(.ai-markdown-surface blockquote) {
        margin: 0.5rem 0 0.75rem;
        padding: 0.5rem 0.9rem;
        border: 1px solid rgb(var(--brand-500) / 0.25);
        background: rgb(var(--brand-500) / 0.08);
        border-radius: 0.6rem;
        color: inherit;
    }

    :global(.dark .ai-markdown-surface blockquote),
    :global([data-theme='dark'] .ai-markdown-surface blockquote) {
        background: rgb(var(--brand-500) / 0.18);
        border-color: rgb(var(--brand-300) / 0.35);
    }

    :global(.ai-markdown-surface a) {
        color: rgb(var(--ai-heading));
        text-decoration: underline;
        text-decoration-thickness: 1px;
        text-underline-offset: 2px;
    }

    :global(.ai-markdown-surface hr) {
        border: none;
        height: 1px;
        margin: 0.6rem 0 0.8rem;
        background: color-mix(in srgb, var(--color-slate-400) 35%, transparent);
    }

    :global(.dark .ai-markdown-surface hr),
    :global([data-theme='dark'] .ai-markdown-surface hr) {
        background: color-mix(in srgb, var(--color-slate-600) 50%, transparent);
    }

    :global(.ai-markdown-surface table) {
        width: 100%;
        border-collapse: collapse;
        margin: 0.5rem 0 0.75rem;
        font-size: 0.82rem;
    }

    :global(.ai-markdown-surface th),
    :global(.ai-markdown-surface td) {
        padding: 0.35rem 0.5rem;
        border-bottom: 1px solid color-mix(in srgb, var(--color-slate-400) 25%, transparent);
        text-align: left;
    }

    :global(.dark .ai-markdown-surface th),
    :global(.dark .ai-markdown-surface td),
    :global([data-theme='dark'] .ai-markdown-surface th),
    :global([data-theme='dark'] .ai-markdown-surface td) {
        border-bottom-color: color-mix(in srgb, var(--color-slate-600) 45%, transparent);
    }

    :global(.ai-markdown-surface th) {
        font-weight: 700;
        color: rgb(var(--ai-code));
        font-size: 0.75rem;
    }

    :global(.ai-markdown-surface > :first-child) {
        margin-top: 0;
    }

    :global(.ai-markdown-surface > :last-child) {
        margin-bottom: 0;
    }

    .ai-bubble {
        position: relative;
        padding: 0.75rem 0.9rem;
        border-radius: 1rem;
        border: 1px solid transparent;
        background: color-mix(in srgb, var(--color-slate-100) 90%, transparent);
        color: rgb(var(--ai-ink));
        box-shadow: 0 8px 16px color-mix(in srgb, var(--color-slate-900) 8%, transparent);
    }

    :global(.dark) .ai-bubble,
    :global([data-theme='dark']) .ai-bubble {
        background: color-mix(in srgb, var(--color-slate-900) 72%, transparent);
    }

    .ai-bubble.ai-surface {
        padding: 1.1rem 1.2rem;
        border-color: rgb(var(--brand-500) / 0.22);
        background: rgb(var(--brand-500) / 0.08);
        box-shadow: none;
    }

    :global(.dark) .ai-bubble.ai-surface,
    :global([data-theme='dark']) .ai-bubble.ai-surface {
        background: rgb(var(--brand-700) / 0.18);
        border-color: rgb(var(--brand-400) / 0.35);
        box-shadow: none;
    }

    .ai-bubble--assistant {
        border-color: rgb(var(--brand-500) / 0.35);
    }

    :global(.theme-bluetit:not(.dark)) .ai-bubble--assistant {
        border-color: rgb(var(--brand-600) / 0.35);
    }
    :global(.theme-bluetit.dark) .ai-bubble--assistant {
        border-color: rgb(var(--brand-400) / 0.40);
    }

    .ai-bubble--user {
        border-color: color-mix(in srgb, var(--color-slate-400) 30%, transparent);
        background: color-mix(in srgb, var(--color-slate-200) 70%, transparent);
    }

    :global(.dark) .ai-bubble--user,
    :global([data-theme='dark']) .ai-bubble--user {
        background: color-mix(in srgb, var(--color-slate-800) 80%, transparent);
    }

    .ai-bubble__role {
        font-size: 0.75rem;
        font-weight: 700;
        color: rgb(var(--ai-muted));
        margin-bottom: 0.4rem;
    }

    .ai-bubble__content {
        font-size: 0.88rem;
        line-height: 1.55;
        white-space: pre-wrap;
    }

    .ai-bubble--assistant .ai-bubble__content {
        white-space: normal;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface h1),
    :global(.ai-bubble--assistant .ai-markdown-surface h2),
    :global(.ai-bubble--assistant .ai-markdown-surface h3),
    :global(.ai-bubble--assistant .ai-markdown-surface h4),
    :global(.ai-bubble--assistant .ai-markdown-surface h5),
    :global(.ai-bubble--assistant .ai-markdown-surface h6) {
        margin-top: 0.5rem;
        margin-bottom: 0.2rem;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface p) {
        margin: 0.2rem 0;
    }

    :global(.ai-bubble--assistant .ai-markdown-surface ul),
    :global(.ai-bubble--assistant .ai-markdown-surface ol) {
        margin: 0.25rem 0 0.55rem;
    }

    .ai-bubble--assistant :global(.ai-markdown-surface p),
    .ai-bubble--assistant :global(.ai-markdown-surface li) {
        color: inherit;
    }

    .ai-thread {
        border-radius: 1.25rem;
        padding: 0.9rem;
        border: 1px solid color-mix(in srgb, var(--color-slate-400) 16%, transparent);
        background: color-mix(in srgb, var(--color-slate-50) 60%, transparent);
        box-shadow: 0 8px 18px color-mix(in srgb, var(--color-slate-900) 6%, transparent);
    }

    :global(.dark) .ai-thread,
    :global([data-theme='dark']) .ai-thread {
        border-color: rgb(var(--brand-400) / 0.18);
        background: color-mix(in srgb, var(--color-slate-950) 22%, transparent);
        box-shadow: 0 10px 22px color-mix(in srgb, var(--color-slate-950) 28%, transparent);
    }
</style>



<div
    data-detection-detail-modal
    class="fixed inset-0 z-50 flex items-center justify-center overflow-y-auto overscroll-contain bg-black/60 p-0 backdrop-blur-xs sm:p-4"
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
        class="relative flex max-h-dvh w-full max-w-5xl flex-col overflow-hidden rounded-none border border-white/20 bg-surface shadow-2xl sm:max-h-[92vh] sm:rounded-2xl"
        role="document"
        tabindex="-1"
    >

        <!-- Reclassification Overlay (covers entire modal content) -->
        {#if reclassifyProgress}
            <ReclassificationOverlay progress={reclassifyProgress} />
        {/if}

        <!-- A strip of its own for the one close button, so nothing scrolls underneath it. -->
        <div class="flex shrink-0 items-center justify-between gap-3 border-b border-line-soft py-1 pl-5 pr-2 sm:pl-6" data-detection-modal-header>
            <p class="min-w-0 text-xs font-semibold text-slate-600 wrap-anywhere dark:text-slate-400">{$_('detection.record_label', { default: 'Detection record' })}</p>
            <DialogCloseButton onclick={onClose} data-detection-modal-close />
        </div>

        <div class="flex-1 overflow-y-auto flex flex-col lg:overflow-hidden lg:grid lg:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)]">
                <div class="flex min-h-0 shrink-0 flex-col bg-slate-950 lg:shrink lg:overflow-y-auto lg:border-r lg:border-slate-200/70 dark:lg:border-slate-700/60">
                    <div class="relative min-w-0 aspect-4/3 min-h-72 shrink-0 overflow-hidden bg-slate-950 sm:aspect-video lg:flex-1" data-detection-photograph>
                        {#if photographDrawnUrl}
                            <img data-detection-media-ambient src={photographDrawnUrl} alt="" aria-hidden="true" class="absolute inset-0 h-full w-full scale-110 object-cover opacity-25 blur-2xl" />
                        {/if}
                        <div class="absolute inset-0 bg-slate-950/55" aria-hidden="true"></div>
                        <!-- The photograph stays drawn under a peek, and only steps aside once the whole
                             scene has actually loaded over it. -->
                        <MediaImage
                            sources={photographSources}
                            alt={detection.display_name}
                            class="relative h-full w-full {photographIsCrop && photographFit === 'cover' ? 'object-cover' : 'object-contain'} {wholeSceneReady ? 'opacity-0' : ''}"
                            placeholderClass="text-slate-600"
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
                                class="absolute inset-0 z-10 {wholeScene.pinned ? 'cursor-zoom-out' : 'cursor-zoom-in'} focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-white"
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
                                ><span class="absolute left-0 top-0 rounded-sm bg-evidence px-1.5 py-0.5 text-3xs font-bold text-slate-950">{$_('detection.frame_chosen_badge', { default: 'Chosen' })}</span></div>
                                {#each wholeScene.otherOutlines as outline}
                                    <div
                                        class="pointer-events-none absolute z-10 rounded-xs border-2 border-dashed border-white/90"
                                        style="left: {outline.left}px; top: {outline.top}px; width: {outline.width}px; height: {outline.height}px;"
                                        data-detection-other-bird-outline
                                        aria-hidden="true"
                                    ></div>
                                {/each}
                            {/if}
                            {#if wholeSceneReady}
                                <span
                                    class="pointer-events-none absolute left-3 top-3 z-30 rounded-full border border-white/15 bg-slate-950/70 px-2.5 py-1 text-2xs font-semibold text-white backdrop-blur-xs"
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
                            class="relative flex shrink-0 flex-col bg-slate-950 {mediaFooterHasActions ? 'pt-4' : ''}"
                            data-detection-media-footer
                        >
                            {#if mediaFooterHasActions}
                            <div class="flex flex-col gap-3 px-5 {showInlineFramePicker ? 'pb-2' : 'pb-5'}">
                                {#if wholeScene.pinned && wholeSceneReady}
                                    <div class="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center" data-detection-whole-scene-actions>
                                        <button
                                            type="button"
                                            class="inline-flex min-h-11 items-center justify-center gap-2 rounded-full border border-white/25 bg-black/55 px-4 text-2xs font-semibold text-white shadow-xl backdrop-blur-xs transition-colors hover:bg-black/70 disabled:cursor-not-allowed disabled:opacity-60 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-white"
                                            disabled={snapshotApplyPending || snapshotGeneratePending}
                                            onclick={(event) => { event.stopPropagation(); void useWholeSceneAsPhotograph(); }}
                                        >
                                            {#if snapshotApplyPending}
                                                <span class="inline-block h-3.5 w-3.5 animate-spin rounded-full border-2 border-current border-t-transparent" aria-hidden="true"></span>
                                            {/if}
                                            {$_('detection.whole_scene_use', { default: 'Use the whole scene as the photograph' })}
                                        </button>
                                        <button
                                            type="button"
                                            class="inline-flex min-h-11 items-center justify-center rounded-full border border-white/25 bg-black/40 px-4 text-2xs font-semibold text-white/85 shadow-xl backdrop-blur-xs transition-colors hover:bg-black/60 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-white"
                                            onclick={(event) => { event.stopPropagation(); resetMediaView(); }}
                                        >
                                            {$_('detection.whole_scene_back', { default: 'Back to the crop' })}
                                        </button>
                                    </div>
                                {/if}

                                {#if canShowFavoriteAction || canPlayVideo || showFetchFullVisitAction || isManualObservation || frigateIssueBadgeVisible}
                                    <div class="flex flex-wrap items-center gap-2" data-detection-media-actions>
                                        {#if canShowFavoriteAction}
                                            <button
                                                type="button"
                                                onclick={handleFavoriteToggle}
                                                disabled={favoritePending}
                                                class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-full border shadow-lg backdrop-blur-xs transition-colors disabled:opacity-60 focus-ring-on-dark {detection.is_favorite ? 'border-brand-300 bg-brand-700/95 text-white hover:bg-brand-800' : 'border-white/35 bg-black/45 text-white hover:bg-black/60'}"
                                                title={detection.is_favorite ? $_('detection.favorite_remove', { default: 'Remove favorite' }) : $_('detection.favorite_add', { default: 'Add favorite' })}
                                                aria-label={detection.is_favorite ? $_('detection.favorite_remove', { default: 'Remove favorite' }) : $_('detection.favorite_add', { default: 'Add favorite' })}
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
                                                class="pointer-events-auto inline-flex h-11 min-w-11 items-center justify-center rounded-full border text-white shadow-xl backdrop-blur-xs transition-colors duration-150 focus:outline-hidden focus:ring-2 focus:ring-focus-on-dark {fullVisitFetched ? 'gap-2 border-brand-300/30 bg-brand-700/95 px-3 hover:bg-brand-700' : 'w-11 border-white/25 bg-black/55 hover:bg-brand-700/90'}"
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
                                            <div class="inline-flex min-h-11 items-center gap-2 rounded-full border border-white/25 bg-black/55 px-3.5 text-xs font-bold text-white shadow-xl backdrop-blur-xs">
                                                <svg class="h-4 w-4 text-brand-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 16V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>
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
                                                class="pointer-events-auto inline-flex min-h-11 items-center gap-2 rounded-full border border-white/25 bg-black/55 px-4 py-2 text-2xs font-semibold text-white shadow-xl backdrop-blur-xs transition-colors duration-150 hover:bg-brand-700/90 disabled:cursor-wait disabled:opacity-75 focus:outline-hidden focus:ring-2 focus:ring-focus-on-dark"
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
                                                class="inline-flex h-11 w-11 items-center justify-center rounded-full border border-rose-200/85 text-rose-700 shadow-lg shadow-rose-500/10 backdrop-blur-xs dark:border-rose-300/20 dark:text-rose-200"
                                                title={videoFailureInsight.summary}
                                                aria-label={videoFailureInsight.summary}
                                                role="img"
                                            >
                                                <img src={FRIGATE_LOGO_URL} alt="" aria-hidden="true" class="h-4 w-4 rounded-[3px] bg-white/95 p-0.5 object-contain" />
                                            </div>
                                        {/if}
                                    </div>
                                {/if}
                            </div>
                            {/if}

                            {#if hasOwnerDetectionActions}
                                <BirdScanControl
                                    eventId={detection.frigate_event}
                                    candidateId={scanFrameCandidate?.candidate_id ?? null}
                                    imageVersion={scanFrameCandidate?.image_url ?? null}
                                    sceneImageUrl={scanFrameCandidate?.image_url ?? null}
                                    disabled={snapshotApplyPending || snapshotGeneratePending || countedBirdsLoading}
                                    oncompleted={(eventId, candidateId) => { void refreshBirdsAfterScan(eventId, candidateId); }}
                                />
                            {/if}
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
                        </div>
                </div>

            <div data-detection-details-column class="flex min-w-0 flex-1 flex-col gap-5 wrap-break-word lg:overflow-y-auto p-5 sm:p-6 {showTagDropdown ? 'blur-xs pointer-events-none select-none' : ''}">
            {#if isManualObservation && detection.observation_notes}
                <div class="border-l-2 border-brand-300 pl-3 dark:border-brand-700">
                    <div class="text-3xs font-bold text-slate-600 dark:text-slate-400">{$_('detection.observation_notes', { default: 'Observation notes' })}</div>
                    <p class="mt-1 whitespace-pre-wrap text-sm leading-6 text-slate-700 dark:text-slate-300">{detection.observation_notes}</p>
                </div>
            {/if}
            {#if isManualObservation && detection.observation_latitude != null && detection.observation_longitude != null}
                <div data-manual-observation-location class="border-l-2 border-slate-300 pl-3 dark:border-slate-600">
                    <div class="flex items-center justify-between gap-3">
                        <div>
                            <div class="text-3xs font-bold text-slate-600 dark:text-slate-400">{$_('manual_observation.location.title', { default: 'Sighting location' })}</div>
                            <p class="mt-1 text-xs tabular-nums text-slate-600 dark:text-slate-300">{detection.observation_latitude.toFixed(5)}, {detection.observation_longitude.toFixed(5)}</p>
                        </div>
                        {#if detection.observation_location_source === 'image_metadata'}
                            <span class="rounded-full bg-slate-100 px-2.5 py-1 text-3xs font-semibold text-slate-600 dark:bg-slate-800 dark:text-slate-300">{$_('manual_observation.location.from_image', { default: 'From image metadata' })}</span>
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
                            <span class="flex h-12 w-12 shrink-0 items-center justify-center rounded-full border border-slate-200 bg-slate-100 text-slate-500 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-400" aria-hidden="true" data-detection-species-reference-placeholder>
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
                                class="h-12 w-12 shrink-0 rounded-full border border-slate-200 object-cover dark:border-slate-700"
                                data-detection-species-reference
                            />
                        {/if}
                    {/if}
                    <div class="min-w-0">
                        <p class="flex items-center gap-1.5 text-3xs font-semibold text-slate-600 dark:text-slate-400">
                        {#if currentClassificationSource === 'manual'}
                            <svg class="h-3.5 w-3.5 text-success-600 dark:text-success-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" d="m5 13 4 4L19 7" />
                            </svg>
                            {authStore.hasOwnerAccess
                                ? $_('detection.identified_by_you', { default: 'Identified by you' })
                                : $_('detection.identified_by_owner', { default: 'Identified by the owner' })}
                        {:else}
                            {$_('detection.identified_as', { default: 'Identified as' })}
                        {/if}
                        </p>
                        <h3 id="detection-modal-title" class="font-display text-2xl font-bold text-slate-900 dark:text-white">{primaryName}</h3>
                        {#if hasOwnerDetectionActions}
                            <ClassificationSource evidence={detection.classification_input} />
                            {#if detection.initial_classification_input && JSON.stringify(detection.initial_classification_input) !== JSON.stringify(detection.classification_input)}
                                <details class="group/original mt-1 text-xs text-slate-600 dark:text-slate-400" data-initial-classification-source>
                                    <summary class="cursor-pointer min-h-11 flex items-center gap-2 rounded-sm focus-visible:ring-2 focus-visible:ring-focus"><svg class="h-3 w-3 group-open/original:rotate-180" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>{$_('detection.named_from.original', { default: 'Original identification' })}</summary>
                                    <ClassificationSource evidence={detection.initial_classification_input} />
                                </details>
                            {/if}
                        {/if}
                        {#if subName && subName !== primaryName}
                            <p class="text-xs italic text-slate-600 dark:text-slate-400">{subName}</p>
                        {/if}
                        <!-- Reads as a link beside the name it is about, not as a button competing with the decisions. -->
                        <button
                            type="button"
                            onclick={handleSpeciesInfo}
                            class="inline-flex min-h-11 items-center gap-1 rounded-sm text-xs font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 focus-ring dark:text-brand-300 dark:hover:text-brand-200"
                            data-detection-species-details
                        >
                            {$_('actions.species_info')}
                            <svg class="h-3 w-3 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M5 12h14m-6-6 6 6-6 6" /></svg>
                        </button>
                    </div>
                </div>

                {#if currentClassificationSource !== 'manual'}
                    <div class="mt-2 flex flex-wrap items-center gap-2.5">
                        <span class="text-sm font-bold tabular-nums text-slate-900 dark:text-white">
                            {Math.round((detection.score || 0) * 100)}%
                        </span>
                        <span class="text-xs text-slate-600 dark:text-slate-400">
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
                                class="btn btn-ghost min-h-11 w-full justify-start rounded-none px-3 text-sm text-red-700 hover:bg-red-50/80 hover:text-red-800 dark:text-red-300 dark:hover:bg-red-950/40 dark:hover:text-red-200"
                                data-detection-delete
                            >
                                <!-- The words on the row are its whole name, so what is read aloud is what is seen. -->
                                <span class="min-w-0 text-left hyphens-auto wrap-anywhere">{$_('actions.delete_detection')}</span>
                            </button>
                        </li>
                    </ul>
                {/if}
            {/if}

            {#if domesticMatch?.declared}
                <div class="card-base space-y-2 p-3 text-sm text-slate-700 dark:text-slate-200" data-detection-domestic-bird>
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
                <div class="p-3 rounded-xl bg-attention-50/80 dark:bg-attention-500/10 border border-attention-200/80 dark:border-attention-500/30 text-attention-900 dark:text-attention-100 flex items-start gap-3" role="status">
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
                                    default: 'Auto-promotion was held back because the video score is below your minimum-confidence floor. Run reclassify to apply this result, or lower the floor in Settings → Detection.',
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
                <div class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-700/60 animate-in fade-in slide-in-from-top-2">
                    <div class="flex items-center justify-between mb-2">
                        <p class="text-3xs font-bold text-slate-700 dark:text-slate-200">
                            {completedClassificationTitle}
                        </p>
                        {#if detection.video_classification_score}
                            <!-- Plain figures like the identification's own score, so it is never the louder of the two. -->
                            <span class="text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-200">
                                {$_('detection.video_analysis.match', { values: { score: (detection.video_classification_score * 100).toFixed(0) } })}
                            </span>
                        {/if}
                    </div>
                    <p class="text-sm font-bold text-slate-800 dark:text-slate-200">
                        {detection.video_classification_label === detection.scientific_name
                            ? $birdNames(detection, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary).primary
                            : detection.video_classification_label}
                    </p>
                    {#if detection.video_result_blocked}
                        <p class="text-3xs font-bold text-slate-700 dark:text-slate-300 mt-0.5">
                            {$_('detection.video_analysis.blocked_label', { default: 'Matched a blocked species: not applied' })}
                        </p>
                    {/if}
                    <!-- What ran it and on which device is diagnostics, not record content. -->
                    <p class="mt-1 text-xs text-slate-600 dark:text-slate-400">
                        {completedClassificationDescription}{#if classificationInputLabel}{' '}&middot; {classificationInputLabel}{/if}
                    </p>
                </div>
            {/if}
            {#if videoAnalysisActive && !reclassifyProgress}
                <div class="p-4 rounded-2xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/70 dark:border-slate-700/50" role="status">
                    <p class="text-xs font-bold text-slate-600 dark:text-slate-300">
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
            <dl class="divide-y divide-slate-200/70 border-y border-slate-200/70 text-xs dark:divide-slate-700/50 dark:border-slate-700/50" data-detection-facts>
                <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                    <dt class="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                        <svg class="h-3.5 w-3.5 shrink-0 text-slate-500 dark:text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" /><path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" /></svg>
                        {$_('detection.fact_seen', { default: 'Seen' })}
                    </dt>
                    <dd class="min-w-0 max-w-full text-right font-medium text-slate-800 dark:text-slate-100">
                        {formatDateTime(detection.detection_time)} &middot; {detection.camera_name}
                    </dd>
                </div>
                {#if weatherSummary}
                    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2" data-detection-weather-row>
                        <dt class="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                            <svg class="h-3.5 w-3.5 shrink-0 text-slate-500 dark:text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M3 15a4 4 0 004 4h9a4 4 0 100-8h-1a5 5 0 10-9 4H7a4 4 0 00-4 4z" /></svg>
                            {$_('detection.fact_conditions', { default: 'Conditions' })}
                        </dt>
                        <dd class="min-w-0 max-w-full text-right font-medium text-slate-800 dark:text-slate-100">
                            {weatherSummary}
                        </dd>
                    </div>
                {/if}
                {#if detection.frigate_score != null}
                    <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                        <dt
                            class="flex items-center gap-2 text-slate-600 dark:text-slate-400"
                            title={$_('detection.fact_frigate_hint', {
                                default:
                                    'How sure the camera was that it had seen a bird at all, before the species was worked out. Separate from the species match above, so the two percentages will differ.'
                            })}
                        >
                            <svg class="h-3.5 w-3.5 shrink-0 text-slate-500 dark:text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2" /></svg>
                            {$_('detection.fact_frigate', { default: 'Spotted as a bird' })}
                        </dt>
                        <dd class="min-w-0 max-w-full text-right font-medium text-slate-800 dark:text-slate-100">
                            {Math.round((detection.frigate_score || 0) * 100)}%
                        </dd>
                    </div>
                {/if}
                {#if birdnetEnabled && !isManualObservation}
                <div class="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 py-2">
                    <dt class="flex items-center gap-2 text-slate-600 dark:text-slate-400">
                        <svg class="h-3.5 w-3.5 shrink-0 text-success-700" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="M9 3h6v11a3 3 0 01-6 0zM5 11a7 7 0 0014 0M12 18v3" /></svg>
                        {$_('detection.fact_heard', { default: 'Heard nearby' })}
                    </dt>
                    <dd class="min-w-0 max-w-full text-right font-medium {effectiveAudioConfirmed ? 'text-success-700 dark:text-success-300' : 'text-slate-600 dark:text-slate-400'}">
                        {audioFactValue}
                    </dd>
                </div>
                {/if}
            </dl>

            {#if detection.is_favorite && archiveFailure}
                <!-- What was not kept, why, and what to do, in words: the heading carries the state, not its colour.
                     Until the archive status is read for this record, it claims nothing about what was kept. -->
                <div class="space-y-1 rounded-xl border border-line-soft px-3 py-2.5 text-sm" data-detection-archive-state="failed" data-detection-archive-view={archiveFailure.kind} aria-live="polite">
                    {#if archiveFailure.kind === 'explained'}
                        <p class="font-semibold text-rose-700 dark:text-rose-300">{archiveFailure.lost}</p>
                        <p class="text-slate-700 dark:text-slate-200" data-detection-archive-cause>{archiveFailure.cause}</p>
                        <p class="text-xs text-slate-600 dark:text-slate-400">{archiveFailure.retry}</p>
                        {#if hasOwnerDetectionActions}
                            <button type="button" class="btn btn-secondary mt-1 min-h-11 px-3 text-xs" disabled={archiveRetrying} onclick={() => { void handleArchiveRetry(); }}>
                                {$_('detection.archive_retry_now', { default: 'Try again now' })}
                            </button>
                        {/if}
                    {:else}
                        <p class="text-slate-700 dark:text-slate-200">{archiveFailure.lost}</p>
                        {#if archiveFailure.kind === 'unchecked'}
                            <button type="button" class="btn btn-secondary mt-1 min-h-11 px-3 text-xs" onclick={() => { archiveCheckAttempt += 1; }} data-detection-archive-check-again>
                                {$_('detection.archive_check_again', { default: 'Check again' })}
                            </button>
                        {/if}
                    {/if}
                </div>
            {:else if detection.is_favorite && archiveLabel}
                <!-- A status of the record, so it is said here in words and never drawn over the photograph. -->
                <p class="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-slate-700 dark:text-slate-200" data-detection-archive-state={archiveState} aria-live="polite">
                    {#if archiveState === 'pending'}
                        <span class="inline-block h-3 w-3 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin" aria-hidden="true"></span>
                    {/if}
                    <span>{archiveLabel}</span>
                </p>
            {/if}

            {#if videoStatusNoticeVisible}
                <div
                    class="p-3 rounded-xl border flex items-start gap-2 {videoStatusNoticeTone.container}"
                    role="status"
                >
                    <svg class="w-4 h-4 shrink-0 mt-0.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                        {#if videoStatusNoticeTone.kind === 'rose'}
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="8" x2="12" y2="12"/>
                            <line x1="12" y1="16" x2="12.01" y2="16"/>
                        {:else if videoStatusNoticeTone.kind === 'attention'}
                            <path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
                            <line x1="12" y1="9" x2="12" y2="13"/>
                            <line x1="12" y1="17" x2="12.01" y2="17"/>
                        {:else}
                            <circle cx="12" cy="12" r="10"/>
                            <line x1="12" y1="16" x2="12" y2="12"/>
                            <line x1="12" y1="8" x2="12.01" y2="8"/>
                        {/if}
                    </svg>
                    <div class="flex flex-col gap-1 min-w-0 flex-1">
                        <span class="text-3xs font-semibold">
                            {videoStatusNoticeTitle}
                        </span>
                        <span class="text-2xs font-normal leading-snug" data-video-status-cause>
                            {videoStatusNoticeDescription}
                        </span>
                        {#if upstreamMissing && detection.frigate_last_checked_at}
                            <span class="text-3xs text-slate-600 dark:text-slate-400">
                                {$_('detection.upstream_missing.last_checked', { default: 'Last checked' })}:
                                {formatDateTime(detection.frigate_last_checked_at)}
                                ·
                                <a
                                    href={FRIGATE_MISSING_DOCS_URL}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    class="font-semibold hover:underline {videoStatusNoticeTone.kind === 'rose' ? 'text-rose-700 dark:text-rose-300' : 'text-brand-700 dark:text-brand-400'}"
                                >
                                    {$_('detection.upstream_missing.learn_more', { default: 'Learn more' })}
                                </a>
                            </span>
                        {/if}
                        {#if videoStatusShowTechnicalDetails}
                            <details class="mt-2 border-t pt-2 {videoStatusNoticeTone.detailsContainer}" bind:open={videoErrorDetailsOpen}>
                                <summary class="flex min-h-11 cursor-pointer select-none items-center text-2xs font-bold focus-ring {videoStatusNoticeTone.detailsSummary}">
                                    {videoErrorDetailsOpen
                                        ? $_('detection.video_analysis.error_details.hide', { default: 'Hide technical details' })
                                        : $_('detection.video_analysis.error_details.show', { default: 'Show technical details' })}
                                </summary>
                                <div class="mt-2 space-y-2 text-2xs text-slate-700 dark:text-slate-300">
                                    {#if videoFailureInsight.errorCode}
                                        <p class="font-mono text-3xs text-slate-600 dark:text-slate-400">
                                            {$_('detection.video_analysis.error_details.error_code', { default: 'Error code: {code}', values: { code: videoFailureInsight.errorCode } })}
                                        </p>
                                    {/if}
                                    {#if videoClassificationDiagnostics}
                                        <section aria-labelledby="video-evidence-heading">
                                            <p id="video-evidence-heading" class="font-bold text-slate-800 dark:text-slate-200">
                                                {$_('detection.video_analysis.evidence.title', { default: 'Evidence from this run' })}
                                            </p>
                                            <p class="mt-0.5 text-slate-600 dark:text-slate-400">
                                                {$_('detection.video_analysis.evidence.summary', {
                                                    default: '{processed} of {sampled} sampled frames were decoded. A frame needed at least {threshold}% confidence to vote.',
                                                    values: {
                                                        processed: videoClassificationDiagnostics.processed_frames,
                                                        sampled: videoClassificationDiagnostics.sampled_frames,
                                                        threshold: Math.round(videoClassificationDiagnostics.minimum_frame_score * 100)
                                                    }
                                                })}
                                            </p>
                                            <dl class="mt-2 divide-y divide-slate-200/80 dark:divide-slate-700/70 border-y-0 border-slate-200/80 dark:border-slate-700/70">
                                                {#each videoClassificationSources as [source, evidence]}
                                                    <div class="py-2 first:pt-0 last:pb-0">
                                                        <div class="flex items-baseline justify-between gap-3">
                                                            <dt class="font-bold text-slate-800 dark:text-slate-200">
                                                                {videoEvidenceSourceLabel(source)}
                                                            </dt>
                                                            <dd class="shrink-0 tabular-nums text-slate-600 dark:text-slate-400">
                                                                {evidence.confident_frames}/{evidence.independent_frames ?? evidence.evaluated_frames}
                                                                {$_('detection.video_analysis.evidence.confident_short', { default: 'confident' })}
                                                            </dd>
                                                        </div>
                                                        <p class="mt-0.5 text-slate-600 dark:text-slate-400">
                                                            {$_('detection.video_analysis.evidence.required', {
                                                                default: 'Needed {required} matching confident moments from this source.',
                                                                values: { required: evidence.required_supporting_frames }
                                                            })}
                                                        </p>
                                                        {#if evidence.top_candidates.length > 0}
                                                            <ul class="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-3xs text-slate-600 dark:text-slate-400" aria-label={$_('detection.video_analysis.evidence.top_candidates', { default: 'Top recurring candidates' })}>
                                                                {#each evidence.top_candidates as candidate}
                                                                    <li>
                                                                        <span class="font-semibold text-slate-700 dark:text-slate-300">{candidate.label}</span>
                                                                        · {candidate.supporting_frames}× · {Math.round(candidate.median_score * 100)}%
                                                                    </li>
                                                                {/each}
                                                            </ul>
                                                        {/if}
                                                    </div>
                                                {/each}
                                            </dl>
                                        </section>
                                    {/if}
                                    {#if videoFailureInsight.causes.length > 0}
                                        <div>
                                            <p class="font-bold text-slate-800 dark:text-slate-200">
                                                {$_('detection.video_analysis.error_details.why', { default: 'Why this can happen' })}
                                            </p>
                                            <ul class="mt-1 list-disc pl-5 space-y-1">
                                                {#each videoFailureInsight.causes as cause}
                                                    <li>{cause}</li>
                                                {/each}
                                            </ul>
                                        </div>
                                    {/if}
                                    {#if videoFailureInsight.checks.length > 0}
                                        <div>
                                            <p class="font-bold text-slate-800 dark:text-slate-200">
                                                {$_('detection.video_analysis.error_details.checks', { default: 'What to check' })}
                                            </p>
                                            <ul class="mt-1 list-disc pl-5 space-y-1">
                                                {#each videoFailureInsight.checks as check}
                                                    <li>{check}</li>
                                                {/each}
                                            </ul>
                                        </div>
                                    {/if}
                                </div>
                            </details>
                        {/if}
                    </div>
                </div>
            {/if}

            {#if hasAudioContext}
                <section data-detection-audio-section class="space-y-3 border-t border-slate-200 pt-5 dark:border-slate-700">
                    <div class="flex items-center gap-3">
                        <div class="min-w-0">
                            <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">
                                {effectiveAudioConfirmed
                                    ? $_('detection.audio_match_evidence', { default: 'The matching call' })
                                    : $_('detection.audio_context')}
                            </p>
                            <!-- A match is stated once, in the facts above with its score; here it is only the evidence. -->
                            {#if !effectiveAudioConfirmed}
                                <p class="text-sm font-bold text-slate-700 dark:text-slate-200 wrap-break-word">
                                    {audioNearbySummary
                                        ? $_('detection.audio_nearby', { values: { species: audioNearbySummary }, default: 'Nearby audio: {species}' })
                                        : $_('detection.audio_no_match_desc', { default: 'No nearby BirdNET species in the matching window' })}
                                </p>
                            {/if}
                        </div>
                    </div>
                    {#if matchedSpectrogramUrl}
                        <figure class="rounded-xl overflow-hidden border border-line-soft bg-slate-900/70 group/spec">
                            <!-- One fixed box whether the picture arrives or not: time runs across the width, as in
                                 the call player, so a failed picture never collapses the row or spills its alt text. -->
                            <div class="relative h-32 sm:h-40" data-record-spectrogram>
                                <!-- svelte-ignore a11y_click_events_have_key_events -->
                                <button
                                    type="button"
                                    class="relative block h-full w-full p-0 m-0 border-0 bg-transparent {matchedAudioClipUrl ? 'cursor-crosshair' : 'cursor-default'}"
                                    onclick={matchedAudioClipUrl ? seekAudioFromSpectrogramClick : undefined}
                                    disabled={!matchedAudioClipUrl}
                                    aria-label={$_('detection.audio_seek_spectrogram_aria', { default: 'Click to seek the audio clip' })}
                                >
                                    {#if failedSpectrogramUrl !== matchedSpectrogramUrl}
                                        <img
                                            src={matchedSpectrogramUrl}
                                            alt={$_('detection.audio_spectrogram_alt', { default: 'BirdNET-Go spectrogram for the matched audio detection' })}
                                            loading="lazy"
                                            class="absolute inset-0 block h-full w-full object-fill pointer-events-none select-none"
                                            onerror={() => { failedSpectrogramUrl = matchedSpectrogramUrl; }}
                                        />
                                    {/if}
                                    {#if matchedAudioClipUrl && audioDuration > 0}
                                        <!-- Trail: short gradient fading amber→transparent
                                             behind the playhead so the eye traces motion -->
                                        <div
                                            class="absolute top-0 bottom-0 w-12 max-w-[15%] pointer-events-none transition-[left] duration-75"
                                            style="left: calc({audioProgressPct}% - 3rem); background: linear-gradient(to right, transparent, rgba(255, 255, 255, 0.12) 55%, rgba(255, 255, 255, 0.3));"
                                            aria-hidden="true"
                                        ></div>
                                        <!-- Playhead cursor -->
                                        <div
                                            class="absolute top-0 bottom-0 w-px bg-white pointer-events-none transition-[left] duration-75"
                                            style="left: {audioProgressPct}%"
                                            aria-hidden="true"
                                        ></div>
                                    {/if}
                                    {#if matchedAudioClipUrl}
                                        <!-- Subtle dim overlay when paused, fades on hover/play
                                             so the play button reads as the obvious affordance -->
                                        <div
                                            class="absolute inset-0 pointer-events-none transition-opacity duration-200 {audioPaused ? 'bg-slate-950/30 opacity-100 group-hover/spec:opacity-60' : 'opacity-0'}"
                                            aria-hidden="true"
                                        ></div>
                                    {/if}
                                </button>
                                {#if failedSpectrogramUrl === matchedSpectrogramUrl}
                                    <p class="pointer-events-none absolute inset-x-0 bottom-0 px-3 py-2 text-3xs text-slate-300" data-record-spectrogram-unavailable>
                                        {$_('detection.audio_spectrogram_unavailable', { default: 'No spectrogram for this call. It can still be played.' })}
                                    </p>
                                {/if}
                                {#if matchedAudioClipUrl}
                                    <!-- Play/pause button: sibling of the spectrogram-click button
                                         (avoids button-in-button), absolutely centered. -->
                                    <button
                                        type="button"
                                        onclick={(e) => { e.stopPropagation(); toggleAudioPlayback(); }}
                                        class="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-12 h-12 rounded-full bg-slate-900/65 hover:bg-slate-900/85 backdrop-blur-md border border-white/25 text-white flex items-center justify-center transition-all duration-150 hover:scale-110 active:scale-95 shadow-lg shadow-black/30 {audioPaused ? 'opacity-95' : 'opacity-0 group-hover/spec:opacity-90'}"
                                        aria-label={audioPaused ? $_('detection.audio_play', { default: 'Play audio clip' }) : $_('detection.audio_pause', { default: 'Pause audio clip' })}
                                    >
                                        {#if audioPaused}
                                            <svg class="w-5 h-5 ml-0.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                                <path d="M8 5v14l11-7z"/>
                                            </svg>
                                        {:else}
                                            <svg class="w-5 h-5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                                <path d="M6 4h4v16H6zM14 4h4v16h-4z"/>
                                            </svg>
                                        {/if}
                                    </button>
                                    {#if audioDuration > 0}
                                        <div class="absolute bottom-1.5 right-2 px-1.5 py-0.5 rounded-md bg-slate-900/75 backdrop-blur-xs text-3xs font-bold text-white/90 tabular-nums pointer-events-none">
                                            {formatAudioClipTime(audioCurrentTime)} / {formatAudioClipTime(audioDuration)}
                                        </div>
                                    {/if}
                                {/if}
                            </div>
                            {#if matchedAudioClipUrl}
                                <!-- Hidden audio element: drives the bound playback state
                                     (currentTime, duration, paused) surfaced by the overlay
                                     button, playhead cursor, trail, and time pill. Native
                                     controls intentionally hidden in favour of the custom UI. -->
                                <audio
                                    bind:this={audioElement}
                                    bind:currentTime={audioCurrentTime}
                                    bind:duration={audioDuration}
                                    bind:paused={audioPaused}
                                    preload="metadata"
                                    src={matchedAudioClipUrl}
                                    class="hidden"
                                    aria-label={$_('detection.audio_clip_aria', { default: 'BirdNET-Go audio clip for the matched detection' })}
                                ></audio>
                            {/if}
                            {#if matchedAudioEntry}
                                <figcaption class="px-3 py-1.5 flex items-center justify-between gap-3 text-3xs font-bold text-slate-200 bg-slate-900/60 backdrop-blur-xs">
                                    <span class="wrap-break-word">{matchedAudioEntry.species}</span>
                                    <span class="flex items-center gap-2 shrink-0">
                                        <span class="text-slate-200">{(matchedAudioEntry.confidence * 100).toFixed(0)}%</span>
                                        <span class="text-slate-300">{formatAudioOffset(matchedAudioEntry.offset_seconds)}</span>
                                    </span>
                                </figcaption>
                            {/if}
                        </figure>
                    {:else if effectiveAudioConfirmed && audioContextLoaded && audioContext.length > 0}
                        <p class="px-3 py-2 rounded-xl bg-slate-100/60 dark:bg-slate-800/40 border border-slate-200/60 dark:border-slate-700/60 text-3xs font-semibold text-slate-600 dark:text-slate-400">
                            {$_('detection.audio_spectrogram_unavailable', { default: 'No spectrogram for this call. It can still be played.' })}
                        </p>
                    {/if}
                    <button
                        type="button"
                        onclick={toggleAudioContext}
                        aria-expanded={audioContextOpen}
                        class="flex min-h-11 w-full items-center justify-between rounded-xl border border-slate-200/60 bg-slate-100/70 px-3 py-2 text-2xs font-semibold text-slate-600 focus-ring dark:border-slate-700/60 dark:bg-slate-800/60 dark:text-slate-300"
                    >
                        <span class="flex items-center gap-2">
                            <svg class="w-3 h-3 transition-transform {audioContextOpen ? '-rotate-90' : 'rotate-0'}" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
                            </svg>
                            {$_('detection.audio_context_all', { default: 'All calls heard around this visit' })}
                        </span>
                        <span class="text-3xs font-bold text-slate-600 dark:text-slate-400">{audioContextOpen ? $_('common.hide') : $_('common.show')}</span>
                    </button>
                    {#if audioContextOpen}
                        <div class="rounded-2xl border border-slate-200/60 dark:border-slate-700/60 bg-white/70 dark:bg-slate-900/40 p-3 space-y-2">
                            {#if audioContextLoading}
                                <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">{$_('detection.audio_context_loading')}</p>
                            {:else if audioContextError}
                                <p class="text-3xs font-semibold text-rose-500">{audioContextError}</p>
                            {:else if audioContext.length === 0 && audioContextSuppressed > 0}
                                <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">
                                    {$_('detection.audio_context_suppressed', {
                                        values: { count: audioContextSuppressed },
                                        default:
                                            'Nearby audio was heard, but on a microphone this camera is not mapped to. Change the sensor mapping in Settings to include it.'
                                    })}
                                </p>
                            {:else if audioContext.length === 0}
                                <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">{$_('detection.audio_context_empty')}</p>
                            {:else}
                                {#each audioContext as audio}
                                    <div class="flex items-center justify-between gap-3 text-xs text-slate-600 dark:text-slate-300">
                                        <div class="min-w-0">
                                            <p class="font-semibold wrap-break-word">{audio.species}</p>
                                            <p class="text-3xs text-slate-600 dark:text-slate-400">
                                                {(audio.confidence * 100).toFixed(0)}%
                                                {#if audio.sensor_id}
                                                    <span class="ml-1 opacity-70">{audio.sensor_id}</span>
                                                {/if}
                                            </p>
                                        </div>
                                        <div class="text-3xs font-bold text-slate-600 dark:text-slate-400">
                                            {formatAudioOffset(audio.offset_seconds)}
                                        </div>
                                    </div>
                                {/each}
                            {/if}
                        </div>
                    {/if}
                </section>
            {/if}


            {#if !isUnknownSpecies && detection.scientific_name}
                <TaxonomyLineage scientificName={detection.scientific_name} />
            {/if}

            {#if !isUnknownSpecies && (speciesInfoLoading || speciesInfo || speciesInfoError || showEbirdNearby)}
                <section data-detection-reference class="space-y-3">
                    <h4 class="text-xs font-semibold text-slate-600 dark:text-slate-400">
                        {$_('detection.reference_disclosure', {
                            values: { species: primaryName },
                            default: 'About {species}, and nearby sightings'
                        })}
                    </h4>

                <div class="space-y-4">
                    {#if enrichmentSummaryProvider !== 'disabled'}
                        <!-- A few lines to recognise the bird by, and a link for the rest: the full
                             article belongs at its source, not in the record. -->
                        <div data-detection-reference-summary>
                            {#if speciesInfoLoading}
                                <div class="flex flex-col gap-2" role="status" aria-label={$_('common.loading', { default: 'Loading' })}>
                                    <div class="h-3 w-3/4 rounded-sm bg-slate-200 motion-safe:animate-pulse dark:bg-slate-700"></div>
                                    <div class="h-3 w-full rounded-sm bg-slate-200 motion-safe:animate-pulse dark:bg-slate-700"></div>
                                    <div class="h-3 w-5/6 rounded-sm bg-slate-200 motion-safe:animate-pulse dark:bg-slate-700"></div>
                                </div>
                            {:else if speciesInfoError}
                                <p class="text-xs text-slate-600 dark:text-slate-400" role="status">{speciesInfoError}</p>
                            {:else if speciesInfo}
                                {@const summaryText = speciesInfo.extract || speciesInfo.description}
                                {@const summaryUrl = speciesInfo.summary_source_url || speciesInfo.wikipedia_url || speciesInfo.source_url}
                                {@const summaryLabel = speciesInfo.summary_source || speciesInfo.source}
                                {#if summaryText}
                                    <!-- Only shortened when the rest can be reached. -->
                                    <p class="text-sm leading-relaxed text-slate-700 dark:text-slate-300 {summaryUrl ? 'line-clamp-3' : ''}" data-detection-reference-text>
                                        {summaryText}
                                    </p>
                                {:else}
                                    <p class="text-xs text-slate-600 dark:text-slate-400">{$_('species_detail.no_info')}</p>
                                {/if}
                                <div class="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-slate-400">
                                    {#if summaryUrl}
                                        <a
                                            href={summaryUrl}
                                            target="_blank"
                                            rel="noopener noreferrer"
                                            class="inline-flex min-h-6 items-center gap-1 rounded-sm font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus dark:text-brand-300 dark:hover:text-brand-200"
                                            data-detection-reference-link
                                        >
                                            {summaryLabel
                                                ? $_('detection.reference_read_more_on', { values: { source: summaryLabel }, default: 'Read more on {source}' })
                                                : $_('detection.reference_read_more', { default: 'Read more' })}
                                            <svg class="h-3 w-3 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
                                            </svg>
                                        </a>
                                    {:else if summaryLabel}
                                        <span>{$_('detection.reference_source', { values: { source: summaryLabel }, default: 'Source: {source}' })}</span>
                                    {/if}
                                    {#if speciesInfo.conservation_status}
                                        <span>{$_('detection.reference_conservation', { values: { status: speciesInfo.conservation_status }, default: 'Conservation status: {status}' })}</span>
                                    {/if}
                                </div>
                            {/if}
                        </div>
                    {/if}

                    {#if showEbirdNearby}
                        <div class="rounded-2xl border border-line-soft p-5">
                            <div class="flex items-center justify-between gap-3 mb-4">
                                <div class="flex items-center gap-2">
                                    <div class="flex flex-col">
                                        <p class="text-3xs font-semibold text-slate-700 dark:text-slate-200">{$_('species_detail.recent_sightings')}</p>
                                        <div class="flex items-center gap-1.5 mt-0.5">
                                            <span class="text-3xs font-bold text-slate-700 dark:text-slate-200">eBird</span>
                                            <span class="w-0.5 h-0.5 rounded-full bg-slate-400"></span>
                                            <span class="text-3xs font-medium text-slate-600 dark:text-slate-400">{ebirdRadiusLabel} · {ebirdDaysBack}d</span>
                                        </div>
                                    </div>
                                </div>
                            </div>

                            {#if !ebirdEnabled}
                                <div class="text-center py-4 rounded-xl bg-white/50 dark:bg-slate-900/30 border border-dashed border-slate-300 dark:border-slate-700">
                                    <p class="text-xs font-medium text-slate-600 dark:text-slate-400">{$_('detection.ebird_enable_sightings')}</p>
                                    <a href="/settings/integrations" class="mt-2 inline-flex min-h-6 items-center text-3xs font-bold text-brand-700 underline underline-offset-2 focus-ring rounded-sm dark:text-brand-300">{$_('detection.ebird_configure_settings')}</a>
                                </div>
                            {:else if ebirdNearbyLoading}
                                <div class="space-y-3">
                                    {#each [1, 2, 3] as _}
                                        <div class="flex justify-between gap-4">
                                            <div class="h-3 w-2/3 bg-slate-200 dark:bg-slate-700 rounded-sm animate-pulse"></div>
                                            <div class="h-3 w-1/4 bg-slate-200 dark:bg-slate-700 rounded-sm animate-pulse"></div>
                                        </div>
                                    {/each}
                                </div>
                            {:else if ebirdNearbyError}
                                <div class="flex items-center gap-2 p-3 rounded-xl bg-rose-50 dark:bg-rose-900/20 text-rose-700 dark:text-rose-400 border border-rose-100 dark:border-rose-800/30">
                                    <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                                    <p class="text-xs font-semibold">{ebirdNearbyError}</p>
                                </div>
                            {:else if (ebirdNearby?.results?.length || 0) === 0}
                                <div class="text-center py-6">
                                    <p class="text-sm text-slate-600 dark:text-slate-400 font-medium">{$_('detection.ebird_none_nearby')}</p>
                                    <p class="text-3xs text-slate-600 dark:text-slate-400 mt-1">{$_('detection.ebird_try_radius')}</p>
                                </div>
                            {:else if ebirdNearby}
                                {#if ebirdNearby.results.some(r => r.lat && r.lng)}
                                    <div class="h-48 mb-4 rounded-xl overflow-hidden border border-line-soft relative z-0">
                                        <Map
                                            markers={ebirdNearby.results
                                                .filter(r => r.lat && r.lng)
                                                .map(r => ({
                                                    lat: r.lat!,
                                                    lng: r.lng!,
                                                    title: r.location_name || 'Unknown Location',
                                                    popupLines: (() => {
                                                        const t = get(_);
                                                        const countLabel = t('species_detail.count_label', { default: 'Count' });
                                                        return [formatEbirdDate(r.observed_at), `${countLabel}: ${r.how_many ?? '?'}`];
                                                    })()
                                                }))}
                                            userLocation={authStore.canModify && settingsStore.settings?.location_latitude && settingsStore.settings?.location_longitude ? [settingsStore.settings.location_latitude, settingsStore.settings.location_longitude] : null}
                                            zoom={10}
                                            obfuscate={!authStore.canModify}
                                        />
                                    </div>
                                {/if}
                                <div class="space-y-2">
                                    {#each ebirdNearby.results.slice(0, 5) as obs}
                                        <div class="flex items-start justify-between gap-3 p-2.5 rounded-xl bg-white/60 dark:bg-slate-900/40 border border-line-soft transition-colors">
                                            <div class="min-w-0">
                                                <p class="text-xs font-bold text-slate-700 dark:text-slate-200 wrap-break-word">{obs.location_name || $_('common.unknown_location')}</p>
                                                <div class="flex items-center gap-2 mt-0.5">
                                                    <p class="text-3xs font-medium text-slate-600 dark:text-slate-400">{formatEbirdDate(obs.observed_at)}</p>
                                                    {#if obs.obs_valid}
                                                        <span
                                                            class="w-1 h-1 rounded-full bg-success-500"
                                                            title={$_('detection.ebird.valid_observation', { default: 'Valid observation' })}
                                                        ></span>
                                                    {/if}
                                                </div>
                                            </div>
                                            {#if obs.how_many}
                                                <span class="shrink-0 px-2 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-3xs font-bold text-slate-700 dark:text-slate-200">
                                                    x{obs.how_many}
                                                </span>
                                            {/if}
                                        </div>
                                    {/each}
                                </div>
                            {/if}
                        </div>
                    {/if}

                </div>
                </section>
            {/if}

            {#if canShowInat}
                <div class="p-4 rounded-2xl border border-line-soft space-y-3">
                    <div class="flex items-center justify-between gap-3">
                        <div class="flex items-center gap-3">
                            <div>
                                <p class="text-3xs font-semibold text-slate-700 dark:text-slate-200">{$_('detection.inat.title')}</p>
                                {#if inatConnectedUser}
                                    <p class="text-xs font-semibold text-slate-700 dark:text-slate-200">{$_('detection.inat.connected', { values: { user: inatConnectedUser } })}</p>
                                {/if}
                            </div>
                        </div>
                        <button
                            type="button"
                            onclick={openInatPanel}
                            class="btn btn-secondary min-h-11 px-3 text-xs"
                            aria-label={$_('detection.inat.open_label')}
                        >
                            {inatPanelOpen ? $_('detection.inat.close') : $_('detection.inat.open')}
                        </button>
                    </div>

                    {#if inatPanelOpen}
                        <div class="space-y-3">
                            {#if inatLoading}
                                <div class="text-xs font-semibold text-slate-600 dark:text-slate-300" role="status">{$_('detection.inat.loading')}</div>
                            {:else}
                                {#if inatError}
                                    <div class="text-xs font-semibold text-rose-600">{inatError}</div>
                                {/if}
                                {#if inatDraft}
                                    <div class="grid grid-cols-2 gap-3 text-2xs text-slate-600 dark:text-slate-300">
                                        <div class="rounded-xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                            <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">{$_('detection.inat.species')}</p>
                                            <p class="font-semibold text-slate-700 dark:text-slate-200">{inatDraft.species_guess}</p>
                                        </div>
                                        <div class="rounded-xl bg-white/80 dark:bg-slate-900/40 border border-slate-200/60 dark:border-slate-700/60 p-2">
                                            <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">{$_('detection.inat.observed')}</p>
                                            <p class="font-semibold text-slate-700 dark:text-slate-200">{formatDateTime(inatDraft.observed_on_string)}</p>
                                        </div>
                                    </div>
                                    <div class="grid grid-cols-2 gap-3">
                                        <div>
                                            <label for="inat-lat" class="block text-3xs font-semibold text-slate-600 dark:text-slate-400 mb-1">{$_('detection.inat.latitude')}</label>
                                            <input
                                                id="inat-lat"
                                                type="number"
                                                step="0.0001"
                                                bind:value={inatLat}
                                                class="input-base"
                                            />
                                        </div>
                                        <div>
                                            <label for="inat-lon" class="block text-3xs font-semibold text-slate-600 dark:text-slate-400 mb-1">{$_('detection.inat.longitude')}</label>
                                            <input
                                                id="inat-lon"
                                                type="number"
                                                step="0.0001"
                                                bind:value={inatLon}
                                                class="input-base"
                                            />
                                        </div>
                                    </div>
                                    <div>
                                        <label for="inat-place" class="block text-3xs font-semibold text-slate-600 dark:text-slate-400 mb-1">{$_('detection.inat.place')}</label>
                                        <input
                                            id="inat-place"
                                            type="text"
                                            bind:value={inatPlace}
                                            class="input-base"
                                        />
                                    </div>
                                    <div>
                                        <label for="inat-notes" class="block text-3xs font-semibold text-slate-600 dark:text-slate-400 mb-1">{$_('detection.inat.notes')}</label>
                                        <textarea
                                            id="inat-notes"
                                            rows="3"
                                            bind:value={inatNotes}
                                            class="input-base"
                                        ></textarea>
                                    </div>
                                    <button
                                        type="button"
                                        onclick={submitInat}
                                        disabled={inatSubmitting}
                                        class="btn btn-primary min-h-11 w-full px-4 text-xs"
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
            {#if llmReady && aiAnalysis}
                <div class="space-y-3">
                    <div class="ai-panel ai-surface">
                        <div class="ai-panel__label">{$_('detection.ai.insight')}</div>
                        <div class="ai-panel__content ai-markdown ai-markdown-surface">
                            <MarkdownText text={aiAnalysis} />
                        </div>
                    </div>
                    {#if authStore.canModify && llmReady}
                        <button
                            onclick={() => handleAIAnalysis(true)}
                            disabled={analyzingAI}
                            class="w-full py-2 px-4 bg-brand-500/10 hover:bg-brand-500/20 text-brand-700 dark:text-brand-400 font-semibold text-sm rounded-xl transition-all flex items-center justify-center gap-2 border border-brand-500/20 disabled:opacity-50 disabled:cursor-not-allowed"
                            title={$_('detection.ai.regenerate_warning', { default: 'Regenerate analysis (clears AI conversation history for this detection)' })}
                        >
                            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                            </svg>
                            {analyzingAI ? $_('detection.ai.regenerating') : $_('detection.ai.regenerate')}
                        </button>
                        {#if conversationTurns.length > 0}
                            <p class="text-3xs font-semibold text-slate-600 dark:text-slate-400">
                                {$_('detection.ai.regenerate_clears_chat_note', { default: 'Note: Regenerating clears the AI conversation history for this detection.' })}
                            </p>
                        {/if}
                    {/if}
                </div>
            {:else if llmReady && !analyzingAI && authStore.canModify}
                <button
                    onclick={() => handleAIAnalysis()}
                    class="w-full py-3 px-4 bg-brand-500/10 hover:bg-brand-500/20 text-brand-700 dark:text-brand-400 font-bold rounded-xl transition-all flex items-center justify-center gap-2 border border-brand-500/20"
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
                    </svg>
                    {$_('detection.ai.ask')}
                </button>
            {:else if analyzingAI}
                <div class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-bold rounded-xl flex items-center justify-center gap-3 animate-pulse">
                    <div class="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
                    {$_('detection.ai.analyzing')}
                </div>
            {/if}

            {#if llmReady && aiAnalysis && authStore.canViewAiConversation}
                <div class="space-y-3">
                    <p class="text-3xs font-bold text-slate-600 dark:text-slate-400">
                        {$_('detection.ai.conversation_title')}
                    </p>
                    <div class="ai-thread">
                    {#if conversationLoading}
                        <div class="w-full py-3 px-4 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 font-bold rounded-xl flex items-center justify-center gap-3 animate-pulse">
                            <div class="w-4 h-4 border-2 border-brand-500 border-t-transparent rounded-full animate-spin"></div>
                            {$_('detection.ai.conversation_loading')}
                        </div>
                    {:else if conversationError}
                        <div class="rounded-xl border border-rose-200 dark:border-rose-800/40 bg-rose-50 dark:bg-rose-900/20 p-3 text-xs text-rose-700 dark:text-rose-300">
                            {conversationError}
                        </div>
                    {:else if conversationTurns.length === 0}
                        <p class="text-xs text-slate-600 dark:text-slate-400">
                            {$_('detection.ai.conversation_empty')}
                        </p>
                    {:else}
                        <div class="space-y-2">
                            {#each conversationTurns as turn}
                                <div class={`ai-bubble ${turn.role === 'assistant' ? 'ai-bubble--assistant ai-surface' : 'ai-bubble--user'}`}>
                                    <div class="ai-bubble__role">
                                        {turn.role === 'assistant' ? $_('detection.ai.assistant') : $_('detection.ai.user')}
                                    </div>
                                    {#if turn.role === 'assistant'}
                                        <div class="ai-bubble__content ai-markdown ai-markdown-surface">
                                            <MarkdownText text={turn.content} />
                                        </div>
                                    {:else}
                                        <div class="ai-bubble__content">{turn.content}</div>
                                    {/if}
                                </div>
                            {/each}
                        </div>
                    {/if}

                    {#if authStore.canModify}
                        <div class="space-y-2">
                            <textarea
                                rows="2"
                                bind:value={conversationInput}
                                placeholder={$_('detection.ai.conversation_placeholder')}
                                class="w-full px-3 py-2 rounded-xl border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 text-xs font-medium text-slate-900 dark:text-slate-100 placeholder:text-slate-400 dark:placeholder:text-slate-500"
                            ></textarea>
                            <button
                                type="button"
                                onclick={sendConversation}
                                disabled={!conversationInput.trim() || conversationSending}
                                class="w-full py-2 px-4 rounded-xl bg-brand-700 hover:bg-brand-800 text-white text-xs font-semibold disabled:opacity-50"
                            >
                                {conversationSending ? $_('detection.ai.sending') : $_('detection.ai.send')}
                            </button>
                        </div>
                    {/if}
                    </div>

                    
                </div>
            {/if}

            <!-- The identifiers, last on screen and last in the tab order. -->
            <RecordTechnicalDetails title={$_('detection.id')} identifier={detection.frigate_event} data-detection-technical-identity>
                    {#if frigateEventUrl}
                        <p class="mt-1">
                            <a
                                href={frigateEventUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                class="inline-flex min-h-6 items-center rounded-sm font-semibold text-brand-700 underline underline-offset-2 hover:text-brand-800 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus dark:text-brand-300 dark:hover:text-brand-200"
                                data-frigate-event-link
                            >
                                {$_('detection.open_in_frigate', { default: 'Open in Frigate' })} &nearr;
                            </a>
                        </p>
                    {:else if hasOwnerDetectionActions && !isManualObservation && missingEventMetadataGone}
                        <p class="mt-1 text-slate-600 dark:text-slate-400" data-frigate-event-gone>
                            {$_('detection.open_in_frigate_gone', { default: 'No longer in Frigate' })}
                        </p>
                    {/if}
                    {#if hasOwnerDetectionActions && !isManualObservation}
                        <RangeFallbackNote eventId={detection.frigate_event} />
                    {/if}
            </RecordTechnicalDetails>
            </div>
        </div>

        {#if hasOwnerDetectionActions && showTagDropdown}
            <div
                data-manual-tag-dialog
                class="absolute left-0 right-0 top-0 z-50 flex h-full items-center justify-center overscroll-contain bg-black/40 p-4 backdrop-blur-xs"
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
                    class="mx-2 flex max-h-full w-full max-w-md flex-col overflow-hidden rounded-2xl border border-slate-200 bg-surface shadow-2xl animate-in fade-in zoom-in-95 touch-pan-y dark:border-slate-700"
                    aria-busy={updatingTag}
                >
                    <div class="flex shrink-0 items-center justify-between border-b border-slate-100 px-5 py-2 dark:border-slate-700">
                        <h4 id="manual-tag-dialog-title" class="text-sm font-bold text-slate-800 dark:text-slate-100">
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
                    <div class="shrink-0 border-b border-slate-100 bg-slate-50 p-4 dark:border-slate-700 dark:bg-slate-900/50">
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
                                class="min-h-11 w-full rounded-lg px-4 py-2.5 text-left text-sm font-medium transition-all touch-manipulation hover:bg-brand-50 hover:text-brand-700 disabled:cursor-wait disabled:opacity-60 dark:hover:bg-brand-900/20 dark:hover:text-brand-400 {result.id === detection.display_name ? 'bg-brand-500/10 text-brand-600 font-bold' : 'text-slate-600 dark:text-slate-300'}"
                            >
                                <span class="block text-sm leading-tight">
                                    {names.primary}
                                    {#if isPending}
                                        <span class="ml-2 inline-flex items-center gap-1 text-3xs text-brand-500">
                                            <span class="inline-block h-2 w-2 rounded-full border border-current border-t-transparent animate-spin"></span>
                                            {$_('common.saving')}
                                        </span>
                                    {/if}
                                </span>
                                {#if names.secondary}
                                    <span class="block text-2xs text-slate-600 dark:text-slate-400 italic">{names.secondary}</span>
                                {/if}
                            </button>
                        {/each}
                        {#if searchResults.length === 0}
                            <p class="px-4 py-6 text-sm text-slate-600 dark:text-slate-400 italic text-center">
                                {isSearching ? $_('common.loading') : $_('detection.tagging.no_results')}
                            </p>
                        {/if}
                    </div>
                </div>
            </div>
        {/if}
    </div>
</div>
