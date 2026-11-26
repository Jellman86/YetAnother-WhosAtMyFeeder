<script lang="ts">
    /**
     * One detection as a single scannable row.
     *
     * #270 asked for a denser Explorer, and said why: "What I am interested is
     * comparing the visiting times. So I can scroll the list fast to get to the
     * time I want." So the time leads, at a fixed width in `tabular-nums`, and
     * it is the only column whose digits are meant to line up down the page —
     * that alignment is what makes fast scanning work.
     *
     * The reading order matches the dashboard's field log (time, subject,
     * score) rather than inventing a second list shape for the same data.
     */
    import { _ } from 'svelte-i18n';
    import { SCORE_TEXT, scoreBand } from '../utils/score-tone';
    import type { Detection } from '../api';
    import { birdNames } from '../naming';
    import { formatDate as formatDateValue, formatTime } from '../utils/datetime';
    import { needsReview } from '../utils/visit-grouping';
    import BadgeHint from './BadgeHint.svelte';
    import { explanation } from '../utils/explanation';
    import DetectionPreview from './DetectionPreview.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import type { CompanionSpecies } from '../utils/visit-captures';
    import CompanionSpeciesNote from './CompanionSpeciesNote.svelte';
    import { frameScan } from '../utils/frame-scan';
    import FrameScanRibbon from './FrameScanRibbon.svelte';
    import { canWatchRecordVideo } from '../utils/record-access';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onPlay?: (detection: Detection) => void;
        selectionMode?: boolean;
        selected?: boolean;
        /** Other species seen in one capture of this visit, and that capture. */
        companions?: CompanionSpecies | null;
        /** Heard calls that fold into this visit because they confirm it. */
        matchedCalls?: number;
        /** Whether a person confirmed this record's species, and of what that is true. */
        ownerConfirmation?: 'visit' | 'capture' | null;
        /** Opens the capture the other species were seen in. */
        onopenCapture?: (capture: Detection) => void;
        /** The open detail view already shows this detection's scan. */
        hideProgress?: boolean;
    }

    let { detection, onclick, onPlay, selectionMode = false, selected = false, companions = null, matchedCalls = 0, ownerConfirmation = null, onopenCapture, hideProgress = false }: Props = $props();

    /** Today and Yesterday by name; anything older by date. Matches the card. */
    const dayLabel = $derived.by(() => {
        try {
            const date = new Date(detection.detection_time);
            const today = new Date();
            const yesterday = new Date(today);
            yesterday.setDate(yesterday.getDate() - 1);
            if (date.toDateString() === today.toDateString()) return $_('common.today');
            if (date.toDateString() === yesterday.toDateString()) return $_('common.yesterday');
            return formatDateValue(date);
        } catch {
            return '';
        }
    });

    const showCommon = $derived(settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true);
    const preferSci = $derived(settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false);
    const naming = $derived($birdNames(detection, showCommon, preferSci));

    // A visit is named by its own species; another species in one capture is a note beneath.
    const primaryName = $derived(naming.primary);
    const subName = $derived(naming.secondary);
    const isFavorite = $derived(!!detection.is_favorite);
    const isManualObservation = $derived(detection.observation_source === 'manual_upload');
    const hasAudioConfirmed = $derived(!isManualObservation && !!detection.audio_confirmed);
    const upstreamMissing = $derived(!isManualObservation && detection.frigate_status === 'missing');
    const canPlayVideo = $derived(!!onPlay && canWatchRecordVideo(authStore) && !!detection.has_clip);

    const rowSubject = $derived(`${primaryName}, ${formatTime(detection.detection_time)}`);
    const openLabel = $derived(
        $_('events.row_open', { values: { species: rowSubject }, default: `Open ${rowSubject}` })
    );
    const selectLabel = $derived(
        $_('events.row_select', { values: { species: rowSubject }, default: `Select ${rowSubject}` })
    );

    const score = $derived(Math.round((detection.score ?? 0) * 100));

    /**
     * A running reclassification is drawn faintly behind the row, like a sonogram under a field
     * note, so the row keeps its height and its time column. The bars are too faint to carry
     * meaning, so the score column states the progress in words while the scan runs, and the
     * row's small text steps one shade darker to stay at AA contrast over the strongest bars.
     */
    const scanProgress = $derived(
        hideProgress ? null : (detectionsStore.getReclassificationProgress(detection.frigate_event) ?? null)
    );
    const scan = $derived(scanProgress ? frameScan(scanProgress) : null);
    // A snapshot fallback has no frames to draw, only a share of the work done.
    const scanFromSnapshot = $derived((scanProgress?.fallbackFrom ?? '').toLowerCase() === 'video');
    const snapshotPercent = $derived(
        scanProgress && scan ? Math.round((Math.min(scan.total, Math.max(0, scanProgress.currentFrame || 0)) / scan.total) * 100) : 0
    );
    const scanStatus = $derived(
        scan?.complete
            ? $_('detection.card_analysis.finalizing_subtitle', { default: 'Applying the best match' })
            : scanFromSnapshot
              ? $_('detection.card_analysis.snapshot_subtitle', { default: 'Using the best available snapshot' })
              : $_('detection.card_analysis.video_subtitle', { default: 'Scanning video frames' })
    );
    const scanValueText = $derived(
        !scan
            ? ''
            : scanFromSnapshot
              ? `${snapshotPercent}%`
              : scan.complete
                ? $_('detection.frame_scan.complete', { values: { total: scan.total }, default: 'All {total} frames read' })
                : $_('detection.frame_scan.value_text', {
                      values: { read: scan.readCount, total: scan.total },
                      default: '{read} of {total} frames read'
                  })
    );

    /**
     * Amber is reserved for "this needs a person", and what counts as needing
     * one is the owner's own classification threshold — the same rule the
     * dashboard's review queue and field log already apply. Inventing a number
     * here would flag a different set of rows to the rest of the app.
     */
    // Read from the public projection: the owner-only settings gave a guest null, and
    // needsReview() answers false on null, so no visitor ever saw a row needing a person.
    const reviewThreshold = $derived(
        settingsStore.settings?.classification_threshold ?? publicSettingsStore.settings?.classification_threshold ?? null
    );
    const needsAttention = $derived(needsReview(detection, reviewThreshold));

    const scoreTone = $derived(SCORE_TEXT[scoreBand(detection.score)]);
</script>

<div
    class="group relative grid grid-cols-[4rem_2.75rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-line-soft px-3 last:border-b-0
           {needsAttention ? 'bg-status-attention-soft' : ''}
           {selected ? 'bg-accent-soft ring-2 ring-inset ring-accent-line' : ''}"
    data-detection-row
    data-frigate-event={detection.frigate_event}
>
    {#if scanProgress && !scanFromSnapshot}
        <!-- Under the subject and score columns only: the time and photo stay clear to scan. -->
        <div class="pointer-events-none absolute bottom-0 left-36 right-3 top-1.5 z-0 opacity-25">
            <FrameScanRibbon progress={scanProgress} variant="backdrop" />
        </div>
    {/if}

    <!-- The whole row is the control, so a thumb lands anywhere along it. -->
    <button
        type="button"
        {onclick}
        class="absolute inset-0 z-0 cursor-pointer rounded-none focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus"
        aria-label={selectionMode ? selectLabel : openLabel}
        aria-pressed={selectionMode ? selected : undefined}
    ></button>

    <div class="pointer-events-none relative z-10 py-2">
        <div class="font-display text-sm font-bold tabular-nums leading-tight text-strong">
            {formatTime(detection.detection_time)}
        </div>
        {#if dayLabel}
            <div class="text-3xs font-semibold text-muted">
                {dayLabel}
            </div>
        {/if}
    </div>

    <!-- The same pop-out the field log uses, so a row and a log entry answer
         "which bird is that" the same way. It reuses the image already fetched,
         opens on focus as well as hover, and closes on Escape. -->
    <div class="relative z-10 flex justify-center">
        <DetectionPreview
            interactive={!selectionMode}
            {detection}
            primaryName={primaryName}
            secondaryName={subName}
            onopen={() => onclick?.()}
        />
    </div>

    <div class="pointer-events-none relative z-10 min-w-0 py-2">
        <div class="flex min-w-0 items-center gap-1.5">
            {#if isFavorite}
                <BadgeHint text={$_('detection.favorite', { default: 'Favourite' })} class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full"><svg class="h-3 w-3 text-accent-ink" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label={$_('detection.favorite', { default: 'Favourite' })}>
                    <path d="M11.05 2.93c.3-.92 1.6-.92 1.9 0l2.02 6.22h6.54c.97 0 1.37 1.24.59 1.81l-5.29 3.84 2.02 6.22c.3.92-.76 1.69-1.54 1.12L12 18.3l-5.29 3.84c-.78.57-1.84-.2-1.54-1.12l2.02-6.22-5.29-3.84c-.78-.57-.38-1.81.59-1.81h6.54l2.02-6.22z" />
                </svg></BadgeHint>
            {/if}
            <span class="truncate text-sm font-bold text-strong">{primaryName}</span>
        </div>
        <div class="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap text-2xs font-semibold {scan ? 'text-muted' : 'text-muted'}">
            {#if scan}
                <span class="shrink-0 text-accent-ink">{scanStatus}</span>
            {:else if needsAttention}
                <BadgeHint text={$_('dashboard.review_session.threshold_note')} class="inline-flex items-center gap-1.5 shrink-0 text-status-attention" data-attention-reason>
                    <span class="attention-dot" aria-hidden="true"></span>{$_('events.row_below_threshold', { default: 'Below the naming threshold' })}
                </BadgeHint>
            {:else if subName && subName !== primaryName}
                <span class="min-w-0 truncate italic">{subName}</span>
            {/if}
            {#if ownerConfirmation}
                <BadgeHint text={ownerConfirmation === 'visit' ? $_('visits.owner_confirmed_hint') : $_('visits.owner_confirmed_capture_hint')} class="inline-flex shrink-0 items-center gap-1 text-status-ok" data-explorer-owner-confirmed={ownerConfirmation}>
                    <svg class="h-3 w-3 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m4 10 4 4 8-8" /></svg>{$_('visits.owner_confirmed')}
                </BadgeHint>
            {/if}
            {#if hasAudioConfirmed}
                <BadgeHint text={$_('detection.audio_evidence_hint')} class="shrink-0 text-accent-ink">
                    {matchedCalls > 0
                        ? $_('events.heard.matching_calls', { values: { count: matchedCalls }, default: 'matching call, {count} calls' })
                        : $_('detection.fact_heard_yes', { default: 'matching call' })}
                </BadgeHint>
            {/if}
            {#if upstreamMissing}
                <BadgeHint text={$_('detection.upstream_missing.card_title')} class="shrink-0 text-orange-700 dark:text-orange-300">
                    {$_('detection.upstream_missing.card_label', { default: 'Missing upstream' })}
                </BadgeHint>
            {/if}
            <span class="min-w-0 truncate">{detection.camera_name}</span>
        </div>
        {#if companions && onopenCapture && !selectionMode}
            <CompanionSpeciesNote {companions} onopen={onopenCapture} />
        {/if}
    </div>

    <div class="relative z-10 flex items-center gap-2 py-2 pl-1">
        {#if canPlayVideo && !selectionMode}
            <button
                type="button"
                onclick={(event) => {
                    event.stopPropagation();
                    onPlay?.(detection);
                }}
                use:explanation={$_('detection.play_video', { values: { species: primaryName } })}
                aria-label={$_('detection.play_video', { values: { species: primaryName } })}
                class="inline-flex h-11 w-11 items-center justify-center rounded-full text-muted transition-colors hover:bg-surface-raised hover:text-accent-ink focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M8 5v14l11-7z" />
                </svg>
            </button>
        {/if}
        {#if scan}
            <div
                class="pointer-events-none min-w-[2.75rem] text-right"
                role="progressbar"
                aria-label={$_('detection.frame_scan.title', { default: 'Video frames read' })}
                aria-valuemin={0}
                aria-valuemax={scanFromSnapshot ? 100 : scan.total}
                aria-valuenow={scanFromSnapshot ? snapshotPercent : scan.readCount}
                aria-valuetext={scanValueText}
            >
                <span class="block font-display text-sm font-bold tabular-nums leading-tight text-accent-ink">
                    {scanFromSnapshot ? `${snapshotPercent}%` : `${scan.readCount}/${scan.total}`}
                </span>
                <span class="block text-3xs font-semibold text-muted">
                    {scanFromSnapshot
                        ? $_('detection.reclassification.analysis', { default: 'Analysis' })
                        : $_('detection.frame_scan.frames_unit', { default: 'frames' })}
                </span>
            </div>
        {:else}
            <div class="pointer-events-none min-w-[2.75rem] text-right">
                <BadgeHint text={$_('detection.confidence_hint', { values: { score } })}
                    class="font-display text-sm font-bold tabular-nums leading-tight {scoreTone}"
                    data-detection-score
                >
                    {score}%
                </BadgeHint>
            </div>
        {/if}
        {#if selectionMode}
            <!-- The card's check: filled when chosen, an empty circle when it can be. -->
            <span
                class="pointer-events-none inline-flex h-6 w-6 items-center justify-center rounded-full border-2
                       {selected
                    ? 'border-accent-line bg-accent text-accent-fg'
                    : 'border-line-strong'}"
                aria-hidden="true"
                data-detection-row-check={selected ? 'selected' : 'unselected'}
            >
                {#if selected}
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                {/if}
            </span>
        {/if}
    </div>
</div>
