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
    import DetectionPreview from './DetectionPreview.svelte';
    import { settingsStore } from '../stores/settings.svelte';
    import { publicSettingsStore } from '../stores/public_settings.svelte';
    import { authStore } from '../stores/auth.svelte';

    interface Props {
        detection: Detection;
        onclick?: () => void;
        onPlay?: (detection: Detection) => void;
        selectionMode?: boolean;
        selected?: boolean;
    }

    let { detection, onclick, onPlay, selectionMode = false, selected = false }: Props = $props();

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

    const naming = $derived.by(() => {
        const showCommon = settingsStore.settings?.display_common_names ?? authStore.displayCommonNames ?? true;
        const preferSci = settingsStore.settings?.scientific_name_primary ?? authStore.scientificNamePrimary ?? false;
        return getBirdNames(detection, showCommon, preferSci);
    });

    const primaryName = $derived(naming.primary);
    const subName = $derived(naming.secondary);
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
    class="group relative grid grid-cols-[3.25rem_2.75rem_minmax(0,1fr)_auto] items-center gap-3 border-b border-slate-200 px-3 last:border-b-0 dark:border-slate-800
           {needsAttention ? 'bg-gradient-to-r from-accent-500/12 to-transparent' : ''}
           {selected ? 'bg-brand-500/10' : ''}"
    data-detection-row
    data-frigate-event={detection.frigate_event}
>
    {#if needsAttention}
        <span class="absolute inset-y-0 left-0 w-[3px] bg-accent-500" aria-hidden="true"></span>
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
            <div class="text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">
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
                <svg class="h-3 w-3 shrink-0 text-amber-500" viewBox="0 0 24 24" fill="currentColor" role="img" aria-label={$_('detection.favorite', { default: 'Favorite' })}>
                    <path d="M11.05 2.93c.3-.92 1.6-.92 1.9 0l2.02 6.22h6.54c.97 0 1.37 1.24.59 1.81l-5.29 3.84 2.02 6.22c.3.92-.76 1.69-1.54 1.12L12 18.3l-5.29 3.84c-.78.57-1.84-.2-1.54-1.12l2.02-6.22-5.29-3.84c-.78-.57-.38-1.81.59-1.81h6.54l2.02-6.22z" />
                </svg>
            {/if}
            <span class="truncate text-sm font-bold text-slate-900 dark:text-white">{primaryName}</span>
        </div>
        <div class="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap text-[11px] font-semibold text-slate-500 dark:text-slate-400">
            {#if needsAttention}
                <span class="shrink-0 text-accent-700 dark:text-accent-300">
                    {$_('events.row_below_threshold', { default: 'Below the naming threshold' })}
                </span>
            {:else if subName && subName !== primaryName}
                <span class="min-w-0 truncate italic">{subName}</span>
            {/if}
            {#if hasAudioConfirmed}
                <span class="shrink-0 text-brand-600 dark:text-brand-400">
                    {$_('detection.fact_heard_yes', { default: 'matching call' })}
                </span>
            {/if}
            {#if upstreamMissing}
                <span class="shrink-0 text-accent-700 dark:text-accent-300">
                    {$_('detection.upstream_missing.card_label', { default: 'Missing upstream' })}
                </span>
            {/if}
            <span class="min-w-0 truncate">{detection.camera_name}</span>
        </div>
    </div>

    <div class="relative z-10 flex items-center gap-2 py-2 pl-1">
        {#if canPlayVideo && !selectionMode}
            <button
                type="button"
                onclick={(event) => {
                    event.stopPropagation();
                    onPlay?.(detection);
                }}
                aria-label={$_('detection.play_video', { values: { species: primaryName } })}
                class="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800 dark:hover:text-brand-400"
            >
                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                    <path d="M8 5v14l11-7z" />
                </svg>
            </button>
        {/if}
        <div class="pointer-events-none min-w-[2.75rem] text-right">
            <div
                class="font-display text-sm font-bold tabular-nums leading-tight {scoreTone}"
            >
                {score}%
            </div>
        </div>
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
</div>
