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
    import type { Detection } from '../api';
    import { getBirdNames } from '../naming';
    import { formatDate as formatDateValue, formatTime } from '../utils/datetime';
    import { needsReview } from '../utils/visit-grouping';
    import BadgeHint from './BadgeHint.svelte';
    import { explanation } from '../utils/explanation';
    import DetectionPreview from './DetectionPreview.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import type { SpeciesInCapture } from '../utils/visit-captures';
    import { frameScan } from '../utils/frame-scan';
    import FrameScanRibbon from './FrameScanRibbon.svelte';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onPlay?: (detection: Detection) => void;
        selectionMode?: boolean;
        selected?: boolean;
        /** Species in the visit's busiest capture, when there is more than one. */
        speciesMix?: SpeciesInCapture[] | null;
        /** That busiest capture, stacked behind the visit's photo so the row reads as several birds. */
        stackFrame?: Detection | null;
        /** Heard calls that fold into this visit because they confirm it. */
        matchedCalls?: number;
        /** Opens the capture the species were counted in. */
        onopenCapture?: () => void;
        /** The open detail view already shows this detection's scan. */
        hideProgress?: boolean;
    }

    let { detection, onclick, onPlay, selectionMode = false, selected = false, speciesMix = null, stackFrame = null, matchedCalls = 0, onopenCapture, hideProgress = false }: Props = $props();
    const uid = $props.id();
    let speciesOpen = $state(false);
    const mixed = $derived((speciesMix?.length ?? 0) >= 2);

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
    const naming = $derived(getBirdNames(detection, showCommon, preferSci));

    const primaryName = $derived(mixed ? $_('events.multiple_species', { default: 'Multiple species' }) : naming.primary);
    const subName = $derived(mixed ? null : naming.secondary);
    const isFavorite = $derived(!!detection.is_favorite);
    const isManualObservation = $derived(detection.observation_source === 'manual_upload');
    const hasAudioConfirmed = $derived(!isManualObservation && !!detection.audio_confirmed);
    const upstreamMissing = $derived(!isManualObservation && detection.frigate_status === 'missing');
    const canPlayVideo = $derived(!!onPlay && !!detection.has_clip);

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

    /** The bands the visual standard sets: under 60 amber, under 85 brand, above green. */
    const scoreTone = $derived(
        (detection.score ?? 0) < 0.6
            ? 'text-accent-700 dark:text-accent-300'
            : (detection.score ?? 0) < 0.85
              ? 'text-brand-700 dark:text-brand-300'
              : 'text-success-700 dark:text-success-300'
    );
</script>

<div
    class="group relative grid grid-cols-[4rem_2.75rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-200 px-3 last:border-b-0 dark:border-slate-800
           {needsAttention ? 'bg-accent-500/10' : ''}
           {selected ? 'bg-brand-500/10' : ''}"
    data-detection-row
    data-frigate-event={detection.frigate_event}
>
    {#if needsAttention}
        <span class="absolute inset-y-0 left-0 w-[3px] bg-accent-500" aria-hidden="true"></span>
    {/if}

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
        class="absolute inset-0 z-0 cursor-pointer rounded-none focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
        aria-label={selectionMode ? selectLabel : openLabel}
    ></button>

    <div class="pointer-events-none relative z-10 py-2">
        <div class="font-display text-sm font-bold tabular-nums leading-tight text-slate-900 dark:text-white">
            {formatTime(detection.detection_time)}
        </div>
        {#if dayLabel}
            <div class="text-3xs font-semibold text-slate-500 dark:text-slate-400">
                {dayLabel}
            </div>
        {/if}
    </div>

    <!-- The same pop-out the field log uses, so a row and a log entry answer
         "which bird is that" the same way. It reuses the image already fetched,
         opens on focus as well as hover, and closes on Escape. -->
    <div class="relative z-10 flex justify-center" data-detection-row-photo={mixed ? 'stack' : 'single'}>
        <!-- A capture with several species stacks its busiest capture behind, as a heard band does. -->
        <DetectionPreview
            interactive={!selectionMode}
            {detection}
            stackBehind={mixed ? (stackFrame ?? detection) : null}
            primaryName={primaryName}
            secondaryName={subName}
            onopen={() => onclick?.()}
        />
    </div>

    <div class="pointer-events-none relative z-10 min-w-0 py-2">
        <div class="flex min-w-0 items-center gap-1.5">
            {#if isFavorite}
                <BadgeHint text={$_('detection.favorite', { default: 'Favorite' })} class="inline-flex h-6 w-6 shrink-0 items-center justify-center rounded-full"><svg class="h-3 w-3 text-amber-500" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label={$_('detection.favorite', { default: 'Favorite' })}>
                    <path d="M11.05 2.93c.3-.92 1.6-.92 1.9 0l2.02 6.22h6.54c.97 0 1.37 1.24.59 1.81l-5.29 3.84 2.02 6.22c.3.92-.76 1.69-1.54 1.12L12 18.3l-5.29 3.84c-.78.57-1.84-.2-1.54-1.12l2.02-6.22-5.29-3.84c-.78-.57-.38-1.81.59-1.81h6.54l2.02-6.22z" />
                </svg></BadgeHint>
            {/if}
            <span class="truncate text-sm font-bold text-slate-900 dark:text-white">{primaryName}</span>
        </div>
        <div class="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap text-2xs font-semibold {scan ? 'text-slate-600 dark:text-slate-300' : 'text-slate-500 dark:text-slate-400'}">
            {#if scan}
                <span class="shrink-0 text-brand-800 dark:text-brand-200">{scanStatus}</span>
            {:else if needsAttention}
                <BadgeHint text={$_('dashboard.review_session.threshold_note')} class="shrink-0 text-accent-700 dark:text-accent-300">
                    {$_('events.row_below_threshold', { default: 'Below the naming threshold' })}
                </BadgeHint>
            {:else if subName && subName !== primaryName}
                <span class="min-w-0 truncate italic">{subName}</span>
            {/if}
            {#if hasAudioConfirmed}
                <BadgeHint text={$_('detection.audio_evidence_hint')} class="shrink-0 text-brand-600 dark:text-brand-400">
                    {matchedCalls > 0
                        ? $_('events.heard.matching_calls', { values: { count: matchedCalls }, default: 'matching call, {count} calls' })
                        : $_('detection.fact_heard_yes', { default: 'matching call' })}
                </BadgeHint>
            {/if}
            {#if upstreamMissing}
                <BadgeHint text={$_('detection.upstream_missing.card_title')} class="shrink-0 text-accent-700 dark:text-accent-300">
                    {$_('detection.upstream_missing.card_label', { default: 'Missing upstream' })}
                </BadgeHint>
            {/if}
            <span class="min-w-0 truncate">{detection.camera_name}</span>
        </div>
        {#if mixed && speciesMix}
            <ul class="mt-1.5 flex flex-wrap gap-1.5" aria-label={$_('events.species_in_capture', { default: 'Species in this capture' })}>
                {#each speciesMix as entry (entry.species)}
                    <li class="inline-flex min-h-6 items-center gap-1.5 rounded-full border border-line-soft bg-surface px-2 text-2xs font-semibold text-slate-700 dark:text-slate-200">
                        {getBirdNames(entry, showCommon, preferSci).primary}<span class="font-bold tabular-nums text-brand-700 dark:text-brand-300">{entry.count}</span>
                    </li>
                {/each}
            </ul>
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
                class="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800 dark:hover:text-brand-400"
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
                <span class="block font-display text-sm font-bold tabular-nums leading-tight text-brand-800 dark:text-brand-300">
                    {scanFromSnapshot ? `${snapshotPercent}%` : `${scan.readCount}/${scan.total}`}
                </span>
                <span class="block text-3xs font-semibold text-slate-600 dark:text-slate-300">
                    {scanFromSnapshot
                        ? $_('detection.reclassification.analysis', { default: 'Analysis' })
                        : $_('detection.frame_scan.frames_unit', { default: 'frames' })}
                </span>
            </div>
        {:else if mixed && !selectionMode}
            <!-- One score cannot speak for several species, so the row offers the species instead. -->
            <button
                type="button"
                class="inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:bg-brand-500/10"
                aria-expanded={speciesOpen}
                aria-controls="{uid}-species"
                onclick={(event) => {
                    event.stopPropagation();
                    speciesOpen = !speciesOpen;
                }}
                data-detection-row-species-toggle
            >
                <span class="hidden sm:inline">{speciesOpen ? $_('events.hide_species', { default: 'Hide species' }) : $_('events.show_species', { default: 'Show species' })}</span>
                <span class="sr-only sm:hidden">{speciesOpen ? $_('events.hide_species', { default: 'Hide species' }) : $_('events.show_species', { default: 'Show species' })}</span>
                <svg class="h-3.5 w-3.5 transition-transform duration-200 motion-reduce:transition-none {speciesOpen ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                    <path d="m5 7 5 5 5-5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
            </button>
        {:else if !mixed}
            <div class="pointer-events-none min-w-[2.75rem] text-right">
                <BadgeHint text={$_('detection.confidence_hint', { values: { score } })}
                    class="font-display text-sm font-bold tabular-nums leading-tight {scoreTone}"
                >
                    {score}%
                </BadgeHint>
            </div>
        {/if}
        {#if selectionMode}
            <span
                class="pointer-events-none inline-flex h-5 w-5 items-center justify-center rounded-md border-2
                       {selected
                    ? 'border-brand-500 bg-brand-500 text-white'
                    : 'border-slate-300 dark:border-slate-600'}"
                aria-hidden="true"
            >
                {#if selected}
                    <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                {/if}
            </span>
        {/if}
    </div>
    {#if mixed && speciesMix}
        <div id="{uid}-species" hidden={!speciesOpen} class="relative z-10 col-span-full -mx-3 border-t border-line-soft bg-surface-raised/50 px-3 py-2 sm:pl-[7.25rem]" data-detection-row-species>
            <ul class="divide-y divide-slate-200/70 dark:divide-slate-800/80">
                {#each speciesMix as entry (entry.species)}
                    <li class="flex min-h-10 items-center justify-between gap-3 text-sm">
                        <span class="font-semibold text-slate-800 dark:text-slate-100">{getBirdNames(entry, showCommon, preferSci).primary}</span>
                        <span class="text-xs font-semibold tabular-nums text-slate-500 dark:text-slate-400">{$_('events.birds_count', { values: { count: entry.count }, default: '{count} birds' })}</span>
                    </li>
                {/each}
            </ul>
            {#if onopenCapture}
                <button type="button" class="btn btn-secondary mt-2 min-h-11 px-3 text-xs" onclick={onopenCapture}>
                    {$_('events.open_capture_birds', { default: 'Open the capture to see each bird' })}
                </button>
            {/if}
        </div>
    {/if}
</div>
