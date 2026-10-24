<script lang="ts">
    /**
     * One Garden capture as an Explorer row, in a visit row's columns: time, photo, subject,
     * score. The worded marker keeps it from reading as a bird, and work that needs a person is
     * flagged the way a low-confidence bird is: tint, bar and a reason in words.
     */
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import type { GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { gardenEntryText, gardenEntryView, gardenVisitLabel, type GardenVisit } from '../utils/garden-explorer';
    import { formatTime } from '../utils/datetime';
    import { relativeDayLabel } from '../utils/day-label';

    let { capture, visit, onopen }: {
        capture: GardenCapture;
        /** The stay or position stack this capture leads, opened together. */
        visit?: GardenVisit;
        onopen: (capture: GardenCapture) => void;
    } = $props();

    let failedUrl = $state<string | null>(null);
    const view = $derived(gardenEntryView(capture));
    const text = $derived(gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback })));
    const photo = $derived(capture.snapshot_url ? withAuthParams(capture.snapshot_url) : null);
    const day = $derived(relativeDayLabel(capture.observed_at, $_));
    const grouped = $derived(gardenVisitLabel(visit, (key, fallback, values) => get(_)(key, { values, default: fallback })));
    const score = $derived(view.score === null ? null : Math.round(view.score * 100));
    const scoreTone = $derived(
        (view.score ?? 0) < 0.6
            ? 'text-amber-800 dark:text-amber-300'
            : (view.score ?? 0) < 0.85
              ? 'text-brand-700 dark:text-brand-300'
              : 'text-success-700 dark:text-success-300'
    );
    const openLabel = $derived(
        $_('garden.explorer.open', { values: { subject: `${text.title}, ${formatTime(capture.observed_at)}` }, default: 'Open Garden capture: {subject}' })
    );
</script>

<div
    class="group relative grid grid-cols-[4rem_2.75rem_minmax(0,1fr)_auto] items-center gap-3 px-3 {view.review ? 'bg-amber-500/10' : ''}"
    data-garden-row={capture.status}
>
    {#if view.review}
        <span class="absolute inset-y-0 left-0 w-[3px] bg-amber-500" aria-hidden="true"></span>
    {/if}
    <!-- The whole row opens the record, where the photograph is shown at the size the decision needs. -->
    <button
        type="button"
        class="absolute inset-0 z-0 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
        aria-label={openLabel}
        onclick={() => onopen(capture)}
    ></button>

    <div class="pointer-events-none relative z-10 py-2">
        <time class="block font-display text-sm font-bold tabular-nums leading-tight text-slate-900 dark:text-white" datetime={capture.observed_at}>{formatTime(capture.observed_at)}</time>
        {#if day}<span class="block text-3xs font-semibold text-slate-500 dark:text-slate-400">{day}</span>{/if}
    </div>

    <div class="pointer-events-none relative z-10 flex justify-center">
        <!-- The bird preview's size and frame, so the column reads as one. -->
        <span class="block h-9 w-9 overflow-hidden rounded-lg border-2 border-white bg-slate-100 dark:border-slate-900 dark:bg-slate-800">
            {#if photo && failedUrl !== photo}
                <img src={photo} alt="" loading="lazy" class="h-full w-full object-cover" onerror={() => (failedUrl = photo)} />
            {/if}
        </span>
    </div>

    <div class="pointer-events-none relative z-10 min-w-0 py-2">
        <!-- The name starts where a bird's does, so the column scans as one; the marker leads the line beneath. -->
        <div class="flex min-w-0 items-center gap-1.5">
            <span class="truncate text-sm font-bold text-slate-900 dark:text-white">{text.title}</span>
        </div>
        <div class="flex min-w-0 items-center gap-2 overflow-hidden whitespace-nowrap text-2xs font-semibold text-slate-500 dark:text-slate-400">
            <GardenExplorerMarker compact />
            <span class="shrink-0 {view.review ? 'text-amber-800 dark:text-amber-300' : ''}">{text.state}</span>
            {#if grouped}<span class="shrink-0">{grouped}</span>{/if}
            <span class="min-w-0 truncate">{capture.camera}</span>
        </div>
    </div>

    <div class="pointer-events-none relative z-10 min-w-[2.75rem] py-2 pl-1 text-right">
        {#if score !== null}
            <span class="font-display text-sm font-bold tabular-nums leading-tight {scoreTone}">{score}%</span>
            <span class="sr-only">{$_('garden.explorer.score_hint', { values: { score }, default: 'Species model score {score}%' })}</span>
        {/if}
    </div>
</div>
