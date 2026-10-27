<script lang="ts">
    /**
     * One Garden animal's visit on the field log's thread, in a bird visit's columns: time, node,
     * photo, name, score, action. The worded Garden marker keeps it from reading as a bird, and
     * work that needs a person is flagged as the Explorer flags it: tint, bar and a reason in words.
     */
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenPhotoPreview from './GardenPhotoPreview.svelte';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import type { GardenServerVisit } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { gardenEntryText, gardenEntryView, gardenVisitLabel } from '../utils/garden-explorer';
    import { formatTime } from '../utils/datetime';

    interface Props {
        visit: GardenServerVisit;
        /** The log's column template, shared so every row lines up. */
        grid: string;
        showCamera: boolean;
        onopen: (visit: GardenServerVisit) => void;
    }

    let { visit, grid, showCamera, onopen }: Props = $props();

    const translate = (key: string, fallback: string, values?: Record<string, string>): string =>
        get(_)(key, { values, default: fallback });

    const capture = $derived(visit.representative);
    const view = $derived(gardenEntryView(capture));
    const text = $derived(gardenEntryText(capture, view, translate));
    const grouped = $derived(
        gardenVisitLabel({ id: visit.id, kind: visit.kind, captureCount: visit.capture_count, items: [capture] }, translate)
    );
    const span = $derived.by(() => {
        const start = formatTime(visit.start_time);
        const end = formatTime(visit.end_time);
        return start === end ? end : `${start}–${end}`;
    });

    let failedUrl = $state<string | null>(null);
    let failedCropUrl = $state<string | null>(null);
    const cropPhoto = $derived(capture.crop_url ? withAuthParams(capture.crop_url) : null);
    const fullPhoto = $derived(capture.snapshot_url ? withAuthParams(capture.snapshot_url) : null);
    const photo = $derived(cropPhoto && cropPhoto !== failedCropUrl ? cropPhoto : fullPhoto);
    const usingSavedCrop = $derived(Boolean(cropPhoto && photo === cropPhoto));

    const score = $derived(view.score === null ? null : Math.round(view.score * 100));
    const scoreTone = $derived(
        (view.score ?? 0) < 0.6
            ? 'text-amber-800 dark:text-amber-300'
            : (view.score ?? 0) < 0.85
              ? 'text-brand-700 dark:text-brand-300'
              : 'text-success-700 dark:text-success-300'
    );
    const barTone = $derived((view.score ?? 0) < 0.6 ? 'bg-amber-500' : (view.score ?? 0) < 0.85 ? 'bg-brand-500' : 'bg-success-500');
    const openLabel = $derived(
        $_('garden.explorer.open', { values: { subject: `${text.title}, ${span}` }, default: 'Open Garden capture: {subject}' })
    );
</script>

<li
    class="{grid} relative items-center gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 sm:py-2.5 dark:border-slate-700/40 {view.review ? 'bg-amber-500/10' : ''}"
    data-field-log-row
    data-row-kind="garden"
    data-field-log-garden={visit.id}
    data-needs-review={view.review ? 'true' : 'false'}
>
    {#if view.review}
        <span class="absolute inset-y-0 left-0 w-[3px] rounded-l-xl bg-amber-500" aria-hidden="true"></span>
    {/if}

    <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">{span}</span>

    <span class="relative flex h-full justify-center" aria-hidden="true">
        <!-- The spine runs behind the nodes so the day reads as one thread. -->
        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
        <span class="relative my-auto h-2 w-2 shrink-0 rounded-full ring-2 ring-white dark:ring-slate-900 {view.review ? 'bg-amber-500' : 'bg-slate-400 dark:bg-slate-500'}"></span>
    </span>

    <!-- The bird preview's size and frame, so the photo column reads as one. -->
    <span class="grid min-h-11 min-w-11 place-items-center" aria-hidden="true">
        <span class="block h-9 w-9 overflow-hidden rounded-lg border-2 border-white bg-slate-100 dark:border-slate-900 dark:bg-slate-800">
            {#if photo && failedUrl !== photo}
                <GardenPhotoPreview {capture} src={photo} cropped={usingSavedCrop} aspect={1} onerror={() => { if (usingSavedCrop) failedCropUrl = photo; else failedUrl = photo; }} />
            {/if}
        </span>
    </span>

    <div class="min-w-0">
        <p class="hyphens-auto break-words text-sm font-semibold leading-5 text-slate-900 dark:text-white" data-field-log-name>
            {text.title}
        </p>
        <p class="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-2xs leading-4 text-slate-500 dark:text-slate-400">
            <GardenExplorerMarker compact />
            {#if score !== null}
                <span class="font-bold tabular-nums sm:hidden {scoreTone}">{score}%</span>
            {/if}
            {#if showCamera}
                <span class="break-words" data-field-log-camera>{capture.camera}</span>
            {/if}
            <span class="font-medium {view.review ? 'text-amber-800 dark:text-amber-300' : ''}" data-field-log-garden-state>{text.state}</span>
            {#if grouped}<span class="font-medium">{grouped}</span>{/if}
        </p>
    </div>

    <span class="hidden flex-col items-end gap-1 sm:flex">
        {#if score !== null}
            <span class="text-xs font-bold tabular-nums {scoreTone}">{score}%</span>
            <span class="sr-only">{$_('garden.explorer.score_hint', { values: { score }, default: 'Species model score {score}%' })}</span>
            <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700" aria-hidden="true">
                <span class="block h-full rounded-full {barTone}" style="width: {score}%"></span>
            </span>
        {/if}
    </span>

    <span class="flex items-center justify-end">
        {#if view.review}
            <button class="btn btn-primary min-h-11 px-2 py-1.5 text-xs sm:px-3" aria-label={openLabel} onclick={() => onopen(visit)}>
                {$_('dashboard.field_log.review', { default: 'Review' })}
            </button>
        {:else}
            <button class="btn btn-ghost min-h-11 min-w-11 px-0 py-1.5 text-xs sm:px-3" aria-label={openLabel} onclick={() => onopen(visit)}>
                <span class="hidden sm:inline">{$_('dashboard.field_log.open', { default: 'Open' })}</span>
                <svg class="h-4 w-4 sm:hidden" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                </svg>
            </button>
        {/if}
    </span>
</li>
