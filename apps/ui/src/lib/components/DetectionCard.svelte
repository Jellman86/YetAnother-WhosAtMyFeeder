<script lang="ts">
    import Separator from './Separator.svelte';
    import type { Snippet } from 'svelte';
    import type { Detection } from '../api';
    import { getThumbnailUrl } from '../api';
    import { detectionsStore } from '../stores/detections.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { SCORE_FILL, scoreBand } from '../utils/score-tone';
    import BadgeHint from './BadgeHint.svelte';
    import { explanation } from '../utils/explanation';
    import DetectionCardAnalysisOverlay from './DetectionCardAnalysisOverlay.svelte';

    import { birdNames } from '../naming';
    import { formatDate as formatDateValue, formatTime } from '../utils/datetime';
    import { photoFitFor, type PhotoFit } from '../utils/photo-fit';
    import type { SpeciesInCapture } from '../utils/visit-captures';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onReclassify?: (detection: Detection) => void;
        onRetag?: (detection: Detection) => void;
        onPlay?: (detection: Detection) => void;
        onFetchFullVisit?: (detection: Detection) => void;
        hideProgress?: boolean;
        index?: number;
        selectionMode?: boolean;
        selected?: boolean;
        fullVisitAvailable?: boolean;
        fullVisitFetched?: boolean;
        fullVisitFetchState?: 'idle' | 'fetching' | 'ready' | 'partial' | 'failed';
        /**
         * Content that belongs to this record, such as its visit's captures. It sits inside the
         * card's one frame, under the record, as a separate control; the card itself still opens
         * the record. Without it the card is the plain, closed shape.
         */
        footer?: Snippet;
        /** Species in the visit's busiest capture, when there is more than one. */
        speciesMix?: SpeciesInCapture[] | null;
        /** Heard calls that fold into this visit because they confirm it. */
        matchedCalls?: number;
        /** Whether a person confirmed this record's species, and of what that is true. */
        ownerConfirmation?: 'visit' | 'capture' | null;
    }

    let {
        detection,
        onclick,
        onReclassify,
        onRetag,
        onPlay,
        onFetchFullVisit: _onFetchFullVisit,
        hideProgress = false,
        index = 0,
        selectionMode = false,
        selected = false,
        fullVisitAvailable: _fullVisitAvailable = false,
        fullVisitFetched = false,
        fullVisitFetchState: _fullVisitFetchState = 'idle',
        footer,
        speciesMix = null,
        matchedCalls = 0,
        ownerConfirmation = null
    }: Props = $props();
    const mixed = $derived((speciesMix?.length ?? 0) >= 2);

    // Check if this detection is being reclassified
    let reclassifyProgress = $derived(!hideProgress ? detectionsStore.getReclassificationProgress(detection.frigate_event) : null);
    let analysisActive = $derived(!!reclassifyProgress);

    // Dynamic Naming Logic
    const showCommon = $derived(settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true);
    const preferSci = $derived(settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false);
    let naming = $derived($birdNames(detection, showCommon, preferSci));

    let primaryName = $derived(mixed ? $_('events.multiple_species', { default: 'Multiple species' }) : naming.primary);
    let subName = $derived(mixed ? null : naming.secondary);
    // While selecting, the card is a toggle named by what it picks, as a list row is.
    const selectSubject = $derived(`${primaryName}, ${formatTime(detection.detection_time)}`);
    const recordLabel = $derived(
        selectionMode
            ? $_('events.row_select', { values: { species: selectSubject }, default: `Select ${selectSubject}` })
            : $_('detection.card_label', { values: { species: primaryName, camera: detection.camera_name } })
    );

    let isManualObservation = $derived(detection.observation_source === 'manual_upload');
    let isVerified = $derived(!isManualObservation && detection.audio_confirmed && detection.score > 0.7);
    let hasAudioConfirmed = $derived(!isManualObservation && !!detection.audio_confirmed);
    let upstreamMissing = $derived(!isManualObservation && detection.frigate_status === 'missing');


    const thumbnailUrl = $derived(
        getThumbnailUrl(detection.frigate_event, detectionsStore.settledMediaVersion(detection.frigate_event))
    );
    // A failure belongs to the address that failed, so a photograph saved by a later run is tried.
    let failedThumbnailUrl = $state<string | null>(null);
    const imageError = $derived(failedThumbnailUrl === thumbnailUrl);
    let imageLoaded = $state(false);
    // Measured per address, so a replacement photograph is fitted afresh.
    let measuredFit = $state<{ url: string; fit: PhotoFit } | null>(null);
    const photoFit = $derived(measuredFit?.url === thumbnailUrl ? measuredFit.fit : 'cover');
    let cardElement = $state<HTMLElement | null>(null);
    let isVisible = $state(false);

    function handleReclassifyClick(event: Event) {
        event.stopPropagation();
        onReclassify?.(detection);
    }

    function handleRetagClick(event: Event) {
        event.stopPropagation();
        onRetag?.(detection);
    }

    function handlePlayClick(event: Event) {
        event.stopPropagation();
        onPlay?.(detection);
    }

    // Lazy load with intersection observer
    $effect(() => {
        if (!cardElement) return;
        const observer = new IntersectionObserver(
            (entries) => {
                if (entries[0].isIntersecting) {
                    isVisible = true;
                    observer.disconnect();
                }
            },
            { rootMargin: '100px' }
        );
        observer.observe(cardElement);
        return () => observer.disconnect();
    });

    function formatDate(dateString: string): string {
        try {
            const date = new Date(dateString);
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            if (date.toDateString() === today.toDateString()) {
                return $_('common.today');
            } else if (date.toDateString() === yesterday.toDateString()) {
                return $_('common.yesterday');
            }
            return formatDateValue(date);
        } catch {
            return '';
        }
    }

    const canPlayVideo = $derived(!!onPlay && (detection.has_clip || fullVisitFetched));
</script>

<div class="relative h-full rounded-4xl transition-all duration-300 ease-out">
    <div
        bind:this={cardElement}
        data-detection-card
        class="group relative bg-surface rounded-2xl
               shadow-xs hover:shadow-md
               border border-line-soft
               hover:border-accent-line/60
               overflow-hidden transition-[border-color,box-shadow] duration-200 ease-out
               flex flex-col h-full
               text-left w-full
               {detection.is_hidden ? 'opacity-60 grayscale-[0.5]' : ''}
               {analysisActive ? 'border-2 border-accent-line ring-2 ring-accent-line' : ''}
               {selectionMode && selected && !analysisActive ? 'border-2 border-accent-line ring-2 ring-accent-line' : ''}"
        style="animation-delay: {index * 40}ms"
    >
    <!-- The record: everything above the footer opens it, and nothing in the footer does. -->
    <div class="relative flex flex-1 flex-col">
    <button
        type="button"
        aria-label={recordLabel}
        aria-pressed={selectionMode ? selected : undefined}
        onclick={onclick}
        class="absolute inset-0 z-10 {footer ? 'rounded-t-2xl' : 'rounded-2xl'} focus:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
    ></button>

    <!-- Reclassification Overlay -->
    {#if analysisActive && reclassifyProgress}
        <div class="absolute inset-0 z-50 pointer-events-none rounded-2xl overflow-hidden">
            <DetectionCardAnalysisOverlay progress={reclassifyProgress} />
        </div>
    {/if}

    <!-- Image Section -->
    <div class="relative aspect-4/3 overflow-hidden">
        {#if !imageError && isVisible}
            {#if !imageLoaded}
                <div class="absolute inset-0 bg-surface-raised animate-shimmer bg-size-[200%_100%] bg-linear-to-r/srgb from-transparent via-line/20 to-transparent"></div>
            {/if}
            {#if photoFit === 'contain'}
                <!-- A tall crop is shown whole over a soft copy of itself, not cut to a band. -->
                <img src={thumbnailUrl} alt="" aria-hidden="true" class="absolute inset-0 h-full w-full scale-110 object-cover opacity-60 blur-xl" data-card-photo-fill />
            {/if}
            <img
                src={thumbnailUrl}
                alt="{$_('detection.image_alt', { values: { species: primaryName, camera: detection.camera_name } })}"
                loading="lazy"
                class="relative w-full h-full {photoFit === 'contain' ? 'object-contain' : 'object-cover'} transition-transform duration-300 ease-out
                       group-hover:scale-[1.025]
                       {imageLoaded ? 'opacity-100' : 'opacity-0'}"
                data-card-photo-fit={photoFit}
                onload={(event) => {
                    imageLoaded = true;
                    measuredFit = { url: thumbnailUrl, fit: photoFitFor(event.currentTarget as HTMLImageElement) };
                }}
                onerror={(event) => failedThumbnailUrl = event.currentTarget.getAttribute('src')}
            />
            
        {:else}
            <div class="absolute inset-0 flex items-center justify-center bg-surface-raised">
                <svg class="w-12 h-12 text-subtle" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        {/if}
        {#if !analysisActive && detection.is_favorite}
            <!-- Only the favourite star sits on the photograph (layout-patterns §5); every reading and
                 every other mark is in the card's body, where it never covers the bird. -->
            <div class="absolute top-3 left-3 z-20">
                    <BadgeHint
                        class="flex h-7 w-7 items-center justify-center rounded-full bg-accent text-accent-fg shadow-md"
                        text={$_('detection.favorite', { default: 'Favorite' })}
                        label={$_('detection.favorite', { default: 'Favorite' })}
                    >
                        <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                            <path d="M11.05 2.927c.3-.921 1.603-.921 1.902 0l2.02 6.217a1 1 0 00.95.69h6.54c.969 0 1.371 1.24.588 1.81l-5.29 3.844a1 1 0 00-.364 1.118l2.02 6.217c.3.921-.755 1.688-1.539 1.118l-5.29-3.844a1 1 0 00-1.175 0l-5.29 3.844c-.783.57-1.838-.197-1.539-1.118l2.02-6.217a1 1 0 00-.364-1.118L.98 11.644c-.783-.57-.38-1.81.588-1.81h6.54a1 1 0 00.95-.69l2.02-6.217z" />
                        </svg>
                    </BadgeHint>
            </div>
        {/if}
        {#if (onReclassify || onRetag) && !analysisActive}
            <div class="absolute bottom-3 right-3 flex gap-2 opacity-0 group-hover:opacity-100 transition-all duration-300 translate-y-2 group-hover:translate-y-0">
                {#if onReclassify && detection.observation_source !== 'manual_upload'}
                    <button
                        onclick={handleReclassifyClick}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                e.stopPropagation();
                                handleReclassifyClick(e);
                            }
                        }}
                        aria-label="{$_('detection.reclassify', { values: { species: primaryName } })}"
                        class="btn btn-secondary btn-icon shadow-lg"
                    >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                        </svg>
                    </button>
                {/if}
                {#if onRetag}
                    <button
                        onclick={handleRetagClick}
                        onkeydown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                                e.preventDefault();
                                e.stopPropagation();
                                handleRetagClick(e);
                            }
                        }}
                        aria-label="{$_('detection.retag', { values: { species: primaryName } })}"
                        class="btn btn-secondary btn-icon shadow-lg"
                    >
                        <svg class="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
                        </svg>
                    </button>
                {/if}
            </div>
        {/if}
    </div>

    <!-- Body -->
    <div class="p-4 flex-1 flex flex-col gap-2.5">
        <!-- Species name -->
        <div>
            <h2 class="wrap-break-word text-lg font-bold leading-tight tracking-tight text-strong" title={primaryName}>
                {primaryName}
            </h2>
            {#if subName}
                <p class="text-2xs italic text-muted font-medium mt-0.5 wrap-break-word opacity-80">
                    {subName}
                </p>
            {/if}
            {#if mixed && speciesMix}
                <ul class="mt-1.5 flex flex-wrap gap-1.5" aria-label={$_('events.species_in_capture', { default: 'Species in this capture' })}>
                    {#each speciesMix as entry (entry.species)}
                        <li class="inline-flex min-h-6 items-center gap-1.5 rounded-full border border-line-soft bg-surface px-2 text-2xs font-semibold text-ink">
                            {$birdNames(entry, showCommon, preferSci).primary}<span class="font-bold tabular-nums text-accent-ink">{entry.count}</span>
                        </li>
                    {/each}
                </ul>
            {/if}
            {#if hasAudioConfirmed && matchedCalls > 0}
                <p class="mt-1 text-2xs font-semibold text-accent-ink">
                    {$_('events.heard.matching_calls', { values: { count: matchedCalls }, default: 'matching call, {count} calls' })}
                </p>
            {/if}
        </div>

        <!-- When and how sure, the marks that qualify the visit, and play, on one line under the name.
             They sit above the record's own button, so each keeps its explanation and its action.
             While selecting, the card owns every click, as a list row does: pointer events are turned
             off on every descendant (not `inert`, which would take the readings from a screen reader). -->
        <!-- The gaps in the line let clicks through to the record; each reading and play takes its
             own. While an analysis covers the card, the readings keep their place (nothing moves when
             it ends) but are inert and hidden: no control under the overlay takes focus or a click. -->
        <div
            class="pointer-events-none relative z-20 mt-auto flex flex-wrap items-center gap-x-3 gap-y-1 {selectionMode ? '[&_*]:pointer-events-none!' : '*:pointer-events-auto'} {analysisActive ? 'invisible' : ''}"
            inert={analysisActive}
            data-detection-card-readings
        >
            <BadgeHint text={$_('detection.captured_at_hint', { values: { date: formatDateValue(detection.detection_time), time: formatTime(detection.detection_time) } })} class="flex min-h-11 items-center gap-1.5 text-xs font-semibold tabular-nums text-ink">
                <svg class="w-3 h-3 text-subtle" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
                {formatTime(detection.detection_time)}
            </BadgeHint>
            {#if !mixed}
            <BadgeHint text={$_('detection.confidence_hint', { values: { score: (detection.score * 100).toFixed(0) } })} class="flex min-h-11 items-center gap-1.5 text-xs font-semibold tabular-nums text-ink">
                <span class="h-2 w-2 rounded-full {SCORE_FILL[scoreBand(detection.score)]}" data-detection-score></span>
                {(detection.score * 100).toFixed(0)}%
            </BadgeHint>
            {/if}
            {#if canPlayVideo}
                <span class="relative inline-flex">
                <button
                    onclick={handlePlayClick}
                    use:explanation={$_('detection.play_video', { values: { species: primaryName } })}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            e.stopPropagation();
                            handlePlayClick(e);
                        }
                    }}
                    aria-label="{$_('detection.play_video', { values: { species: primaryName } })}"
                    class="btn btn-secondary btn-icon rounded-full"
                >
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                        <path d="M8 5v14l11-7z"/>
                    </svg>
                </button>
                {#if fullVisitFetched}
                    <BadgeHint
                        class="absolute -right-0.5 -top-0.5 inline-flex h-4 w-4 items-center justify-center rounded-full border border-surface bg-accent text-accent-fg shadow-md"
                        text={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                        label={$_('video_player.full_visit_ready', { default: 'Full visit clip ready' })}
                    >
                        <svg class="h-2 w-2" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true">
                            <path d="M7 3H5a2 2 0 00-2 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                            <path d="M13 3h2a2 2 0 012 2v2" stroke-linecap="round" stroke-linejoin="round"></path>
                            <path d="M17 13v2a2 2 0 01-2 2h-2" stroke-linecap="round" stroke-linejoin="round"></path>
                            <path d="M7 17H5a2 2 0 01-2-2v-2" stroke-linecap="round" stroke-linejoin="round"></path>
                        </svg>
                    </BadgeHint>
                {/if}
                </span>
            {/if}
            {#if !analysisActive}

            {#if ownerConfirmation}
                <BadgeHint
                    class="flex h-7 w-7 items-center justify-center rounded-full border border-status-ok-line bg-status-ok-soft text-status-ok"
                    text={ownerConfirmation === 'visit' ? $_('visits.owner_confirmed_hint') : $_('visits.owner_confirmed_capture_hint')}
                    label={$_('visits.owner_confirmed')}
                    data-explorer-owner-confirmed={ownerConfirmation}
                >
                    <svg class="w-3.5 h-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m4 10 4 4 8-8" /></svg>
                </BadgeHint>
            {/if}
            {#if isVerified}
                <BadgeHint
                    class="flex h-7 w-7 items-center justify-center rounded-full border border-status-ok-line bg-status-ok-soft text-status-ok"
                    text={$_('detection.audio_evidence_hint')}
                    label={$_('detection.verified')}
                >
                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
                    </svg>
                </BadgeHint>
            {/if}
            {#if hasAudioConfirmed && !isVerified}
                <BadgeHint
                    class="flex h-7 w-7 items-center justify-center rounded-full border border-status-info-line bg-status-info-soft text-status-info"
                    text={$_('detection.audio_evidence_hint')}
                    label={$_('detection.audio_match')}
                >
                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M9 9l10.5-3m0 6.553v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 11-.99-3.467l2.31-.66a2.25 2.25 0 001.632-2.163zm0 0V2.25L9 5.25v10.303m0 0v3.75a2.25 2.25 0 01-1.632 2.163l-1.32.377a1.803 1.803 0 01-.99-3.467l2.31-.66A2.25 2.25 0 009 15.553z" />
                    </svg>
                </BadgeHint>
            {/if}
            {#if detection.observation_source === 'manual_upload'}
                <BadgeHint
                    class="flex h-7 w-7 items-center justify-center rounded-full border border-line bg-surface-raised text-muted"
                    text={$_('detection.manual_upload', { default: 'Added from an upload' })}
                    label={$_('detection.manual_upload', { default: 'Added from an upload' })}
                >
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.2" d="M12 16V4m0 0L8 8m4-4 4 4M5 14v4a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-4" /></svg>
                </BadgeHint>
            {/if}
            {#if upstreamMissing}
                <BadgeHint
                    class="flex h-7 w-7 items-center justify-center rounded-full border border-orange-600 bg-orange-50 text-orange-700 dark:border-orange-400 dark:bg-orange-950 dark:text-orange-300"
                    text={$_('detection.upstream_missing.card_title', { default: 'Frigate no longer has this event or media' })}
                    label={$_('detection.upstream_missing.card_label', { default: 'Missing upstream' })}
                >
                    <svg class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z" />
                    </svg>
                </BadgeHint>
            {/if}
            {/if}
        </div>

        <!-- No weather here: it does not help tell one visit from the next, and the record states it once. -->
        <!-- Compact metadata line: date + camera -->
        <div class="flex items-center gap-1.5 text-2xs text-muted font-medium flex-wrap">
            <span>{formatDate(detection.detection_time)}</span>
            <Separator />
            <span class="wrap-break-word">{detection.camera_name}</span>
        </div>
    </div>
    </div>
    {#if footer}
        <div class="relative z-20" data-detection-card-footer>{@render footer()}</div>
    {/if}
    {#if selectionMode && !analysisActive}
        <!-- Selection is a ring and a filled check, never a veil over the bird: the photo and name
             stay readable, and an empty circle shows the card can be chosen. The button carries
             the state for assistive technology. -->
        <span
            class="pointer-events-none absolute right-3 top-3 z-40 inline-flex h-8 w-8 items-center justify-center rounded-full border-2 shadow-md
                   {selected ? 'border-surface bg-accent text-accent-fg' : 'border-on-media bg-media/35 text-transparent'}"
            aria-hidden="true"
            data-detection-card-check={selected ? 'selected' : 'unselected'}
        >
            <svg class="h-4 w-4" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2.6">
                <path d="M5 10.5l3.2 3.2L15 7" stroke-linecap="round" stroke-linejoin="round"></path>
            </svg>
        </span>
    {/if}
    </div>
</div>
