<script lang="ts">
    /**
     * One Garden animal's visit on the field log's thread, in a bird visit's columns: time, node,
     * photo, name, score, action. The worded Garden marker keeps it from reading as a bird, and
     * work that needs a person is flagged as the Explorer flags it: a faint tint, and an amber dot
     * beside the reason in words.
     */
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenCapturePreview from './GardenCapturePreview.svelte';
    import GardenVisitCaptures from './GardenVisitCaptures.svelte';
    import type { GardenCaptureScope } from '../utils/garden-visit-viewer.svelte';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import type { GardenCapture, GardenServerVisit } from '../api/garden';
    import { gardenEntryText, gardenEntryView, gardenVisitLabel } from '../utils/garden-explorer';
    import { authStore } from '../stores/auth.svelte';
    import { formatTime } from '../utils/datetime';
    import { SCORE_FILL, SCORE_TEXT, scoreBand } from '../utils/score-tone';
    import { FIELD_LOG_CELL as cell } from '../utils/field-log';

    interface Props {
        visit: GardenServerVisit;
        scope?: GardenCaptureScope;
        oncapture?: (capture: GardenCapture, index: number) => void;
        /** The log's column template, shared so every row lines up. */
        grid: string;
        showCamera: boolean;
        onopen: (visit: GardenServerVisit) => void;
    }

    let { visit, scope, oncapture, grid, showCamera, onopen }: Props = $props();

    const translate = (key: string, fallback: string, values?: Record<string, string | number>): string =>
        get(_)(key, { values, default: fallback });

    const capture = $derived(visit.representative);
    const view = $derived(gardenEntryView(capture));
    const text = $derived(gardenEntryText(capture, view, translate, authStore.hasOwnerAccess ? 'owner' : 'visitor'));
    const grouped = $derived(
        gardenVisitLabel({ id: visit.id, kind: visit.kind, captureCount: visit.capture_count, items: [capture] }, translate)
    );
    const span = $derived.by(() => {
        const start = formatTime(visit.start_time);
        const end = formatTime(visit.end_time);
        return start === end ? end : `${start}–${end}`;
    });

    const score = $derived(view.score === null ? null : Math.round(view.score * 100));
    const scoreTone = $derived(SCORE_TEXT[scoreBand(view.score)]);
    const barTone = $derived(SCORE_FILL[scoreBand(view.score)]);
    const openLabel = $derived(
        $_('garden.explorer.open', { values: { subject: `${text.title}, ${span}` }, default: 'Open Garden capture: {subject}' })
    );
</script>

<li
    class="{grid} relative items-center gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 log-wide:py-2.5 dark:border-slate-700/40 {view.review ? 'bg-attention-500/5' : ''}"
    data-field-log-row
    data-row-kind="garden"
    data-field-log-garden={visit.id}
    data-needs-review={view.review ? 'true' : 'false'}
>
    <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400 {cell.time}">{span}</span>

    <span class="relative flex h-full justify-center {cell.node}" aria-hidden="true">
        <!-- The spine runs behind the nodes so the day reads as one thread. -->
        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
        <span class="relative my-auto h-2 w-2 shrink-0 rounded-full ring-2 ring-white dark:ring-slate-900 {view.review ? 'bg-attention-500' : 'bg-slate-400 dark:bg-slate-500'}"></span>
    </span>

    <!-- The bird visit's photo cell and pop-out, so the photo column reads and behaves as one. -->
    <span class="flex {cell.photo}">
        <GardenCapturePreview {capture} fill onopen={() => onopen(visit)} />
    </span>

    <div class="min-w-0 {cell.body}">
        <p class="hyphens-auto wrap-break-word text-sm font-semibold leading-5 text-slate-900 dark:text-white" data-field-log-name>
            {text.title}
        </p>
        <p class="flex flex-wrap items-baseline gap-x-1.5 gap-y-0.5 text-2xs leading-4 text-slate-500 dark:text-slate-400">
            <GardenExplorerMarker compact />
            {#if score !== null}
                <span class="font-bold tabular-nums log-wide:hidden {scoreTone}">{score}%</span>
            {/if}
            {#if showCamera}
                <span class="wrap-break-word" data-field-log-camera>{capture.camera}</span>
            {/if}
            {#if view.review}
                <span class="inline-flex items-center gap-1.5 font-medium text-attention-800 dark:text-attention-300" data-field-log-garden-state data-attention-reason><span class="attention-dot" aria-hidden="true"></span>{text.state}</span>
            {:else}
                <span class="font-medium" data-field-log-garden-state>{text.state}</span>
            {/if}
            {#if grouped && !(scope && oncapture)}<span class="font-medium">{grouped}</span>{/if}
        </p>
    </div>

    <span class="hidden flex-col items-end gap-1 log-wide:flex">
        {#if score !== null}
            <span class="text-xs font-bold tabular-nums {scoreTone}">{score}%</span>
            <span class="sr-only">{$_('garden.explorer.score_hint', { values: { score }, default: 'Species model score {score}%' })}</span>
            <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700" aria-hidden="true">
                <span class="block h-full rounded-full {barTone}" style="width: {score}%"></span>
            </span>
        {/if}
    </span>

    <span class="flex items-center justify-end {cell.action}">
        {#if view.review}
            <button class="btn btn-primary min-h-11 px-2 py-1.5 text-xs log-wide:px-3" aria-label={openLabel} onclick={() => onopen(visit)} data-field-log-action>
                {$_('dashboard.field_log.review', { default: 'Review' })}
            </button>
        {:else}
            <button class="btn btn-ghost min-h-11 min-w-11 px-0 py-1.5 text-xs log-wide:px-3 log-narrow:px-3" aria-label={openLabel} onclick={() => onopen(visit)} data-field-log-action>
                <span class="hidden log-wide:inline log-narrow:inline">{$_('dashboard.field_log.open', { default: 'Open' })}</span>
                <svg class="h-4 w-4 log-wide:hidden" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                </svg>
            </button>
        {/if}
    </span>
    {#if scope && oncapture}
        <div class="col-[3/-1] min-w-0 log-narrow:col-[2/-1]">
            <GardenVisitCaptures visit={{ id: visit.id, kind: visit.kind, captureCount: visit.capture_count, items: [capture] }}
                {scope} layout="inline" onselect={oncapture} />
        </div>
    {/if}
</li>
