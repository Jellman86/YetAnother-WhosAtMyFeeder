<script lang="ts">
    /**
     * One visit on the field log's thread. A visit of several captures opens from its time: the
     * captures join the same thread beneath it, in the same columns, each with its own time to the
     * second. The visit's node is solid; a capture's is hollow on a tinted stretch of the line, and
     * the capture the visit uses as its photo is filled, so the two kinds read apart without colour.
     */
    import { onDestroy, untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import BadgeHint from './BadgeHint.svelte';
    import DetectionPreview from './DetectionPreview.svelte';
    import type { Detection } from '../api';
    import type { DetectionVisit as ServerVisit } from '../api/visits';
    import type { DetectionVisit } from '../utils/visit-grouping';
    import { visitBirdMarker, type VisitBirdMarker } from '../utils/visit-birds';
    import { captureFacts } from '../utils/visit-captures';
    import { VisitCaptureList } from '../utils/visit-capture-list.svelte';
    import { formatTime } from '../utils/datetime';
    import { getBirdNames } from '../naming';
    import { settingsStore } from '../stores/settings.svelte';

    interface Props {
        visit: DetectionVisit;
        /** The log's column template, shared so every row and capture lines up. */
        grid: string;
        showCamera: boolean;
        canIdentify: boolean;
        onselect?: (detection: Detection) => void;
        onidentify?: (detection: Detection) => void;
        onplay?: (detection: Detection) => void;
    }

    let { visit, grid, showCamera, canIdentify, onselect, onidentify, onplay }: Props = $props();

    const uid = $props.id();
    const listId = `${uid}-captures`;
    let open = $state(false);

    function captureList(fallback: ServerVisit): VisitCaptureList {
        return new VisitCaptureList(() => ({ visit: visit.server ?? fallback, window: visit.window ?? {} }));
    }

    // Legacy and fixture visits carry their frames already; only server visits read captures.
    const initialServer = untrack(() => visit.server);
    const list = initialServer ? captureList(initialServer) : null;
    const server = $derived(visit.server ?? initialServer);
    const captureCount = $derived(visit.captureCount ?? visit.frames.length);
    const expandable = $derived(list !== null && (server?.capture_count ?? 0) > 1);
    const expanded = $derived(open && expandable);

    $effect(() => {
        if (!list) return;
        void list.key;
        if (!expanded) return;
        untrack(() => list.ensure());
    });
    onDestroy(() => list?.dispose());

    function names(detection: Detection): { primary: string; secondary: string | null } {
        return getBirdNames(detection, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary);
    }

    const naming = $derived(names(visit.lead));
    const score = $derived(visit.best.score ?? 0);
    const birds = $derived(visitBirdMarker(visit));
    const capturesText = $derived($_('visits.captures', { values: { count: captureCount }, default: '{count} captures' }));
    const span = $derived.by(() => {
        const start = formatTime(visit.startTime);
        const end = formatTime(visit.endTime);
        return start === end ? end : `${start}–${end}`;
    });
    // The visit's node says what it stands for on hover.
    const visitHint = $derived(
        captureCount > 1
            ? $_('visits.node_visit_many', { values: { span, count: captureCount }, default: 'Visit, {span}, {count} captures' })
            : $_('visits.node_visit', { values: { span }, default: 'Visit at {span}' })
    );

    // Captures in one visit are seconds apart, so minutes alone would print the same time twice.
    function captureTime(capture: Detection): string {
        return formatTime(capture.detection_time, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function percent(value: number | null | undefined): number {
        return Math.round((value ?? 0) * 100);
    }

    /** The bands the visual standard sets: under 60 amber, under 85 brand, above green. */
    function scoreTone(value: number): string {
        if (value < 0.6) return 'text-accent-700 dark:text-accent-300';
        if (value < 0.85) return 'text-brand-700 dark:text-brand-300';
        return 'text-success-700 dark:text-success-300';
    }

    function barTone(value: number): string {
        if (value < 0.6) return 'bg-accent-500';
        if (value < 0.85) return 'bg-brand-500';
        return 'bg-success-500';
    }

    function birdsText(marker: VisitBirdMarker): string {
        const { counted, unknown, excluded } = marker.summary;
        if (counted === 0) {
            return $_('dashboard.field_log.birds_none_counted', {
                values: { count: excluded },
                default: 'No birds counted, {count} excluded'
            });
        }
        const text = $_('dashboard.field_log.birds_in_capture', {
            values: { count: counted },
            default: '{count} birds in one capture'
        });
        return unknown > 0
            ? `${text}, ${$_('dashboard.field_log.birds_unknown', { values: { count: unknown }, default: '{count} unknown' })}`
            : text;
    }

    function captureNotes(capture: Detection): { text: string; emphasis: boolean }[] {
        if (!server) return [];
        const facts = captureFacts(capture, server);
        const notes: { text: string; emphasis: boolean }[] = [];
        if (facts.shown) notes.push({ text: $_('visits.shown_photo', { default: 'Visit photo' }), emphasis: true });
        if (facts.birds !== null) notes.push({ text: $_('visits.capture_birds', { values: { count: facts.birds }, default: '{count} birds' }), emphasis: false });
        if (facts.heard) notes.push({ text: $_('detection.fact_heard_yes', { default: 'matching call' }), emphasis: true });
        return notes;
    }
</script>

<!-- A stretch of the thread. Captures tint it so the visit they belong to is visible at a glance. -->
{#snippet branch(dot: 'capture' | null, hint = '')}
    <!-- Two kinds of node only: the visit's solid one, and this ring for each of its captures. The
         visit photo is said in words on its row, so the day's one thread runs on unchanged. -->
    <span class="relative flex h-full justify-center" aria-hidden="true">
        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
        {#if dot === 'capture'}
            <!-- A 20px hover area around the 8px node, so its tooltip is easy to find. -->
            <span class="relative my-auto grid h-5 w-5 cursor-help place-items-center" title={hint} data-field-log-node-hint>
                <span class="h-2 w-2 rounded-full bg-white ring-[1.5px] ring-slate-400 dark:bg-slate-900 dark:ring-slate-500" data-field-log-capture-dot="capture"></span>
            </span>
        {/if}
    </span>
{/snippet}

<li
    class="{grid} items-center gap-y-1 rounded-xl border-b border-slate-200/60 px-2 py-2 last:border-b-0 sm:py-2.5 dark:border-slate-700/40"
    class:bg-gradient-to-r={visit.needsReview}
    class:from-accent-50={visit.needsReview}
    class:dark:from-accent-950={visit.needsReview}
    data-field-log-row
    data-field-log-visit={visit.key}
    data-needs-review={visit.needsReview ? 'true' : 'false'}
>
    {#if expandable}
        <!-- The time is the visit's handle: it opens the captures that make the visit. -->
        <button
            type="button"
            class="-mx-1 min-h-11 self-stretch rounded-lg px-1 text-left text-xs font-medium tabular-nums text-slate-700 transition-colors hover:bg-slate-100 hover:text-slate-950 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-200 dark:hover:bg-slate-800/60 dark:hover:text-white"
            aria-expanded={expanded}
            aria-controls={listId}
            aria-label="{span}, {capturesText}"
            onclick={() => (open = !open)}
            data-field-log-time-toggle
        >
            <span class="block">{span}</span>
        </button>
    {:else}
        <span class="text-xs tabular-nums text-slate-500 dark:text-slate-400">{span}</span>
    {/if}

    <span class="relative flex h-full justify-center" aria-hidden="true">
        <!-- The spine runs behind the nodes so the day reads as one thread. -->
        <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
        <span class="relative my-auto grid h-5 w-5 shrink-0 cursor-help place-items-center" title={visitHint} data-field-log-node-hint>
            <span
                class="h-2 w-2 rounded-full ring-2 ring-white dark:ring-slate-900 {visit.needsReview
                    ? 'bg-accent-500'
                    : 'bg-brand-500'}"
            ></span>
        </span>
    </span>

    <DetectionPreview
        detection={visit.best}
        frames={visit.frames}
        frameCount={captureCount}
        showCount={false}
        primaryName={naming.primary}
        secondaryName={naming.secondary}
        onopen={(frame) => onselect?.(frame)}
    />

    <div class="min-w-0">
        <p class="line-clamp-2 hyphens-auto break-words text-sm font-semibold leading-5 text-slate-900 sm:line-clamp-1 dark:text-white" data-field-log-name>
            {naming.primary}
        </p>
        <!-- Wraps rather than truncates, so a marker is never cut off behind the name. -->
        <p class="flex flex-wrap items-baseline gap-x-1.5 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
            <span class="font-bold tabular-nums sm:hidden {scoreTone(score)}">{percent(score)}%</span>
            {#if showCamera}
                <span class="sm:hidden">{visit.camera}</span>
            {/if}
            {#if visit.needsReview}
                <span class="font-medium text-accent-700 dark:text-accent-300">
                    {$_('dashboard.field_log.needs_name', { default: 'Below the naming threshold' })}
                </span>
            {:else if naming.secondary}
                <span class="hidden min-w-0 truncate italic sm:inline">{naming.secondary}</span>
            {/if}
            {#if captureCount > 1}
                <!-- Captures, not birds: the busiest capture's bird count is stated on its own. -->
                <span class="font-medium {expandable ? 'hidden sm:inline' : ''}" data-field-log-captures>{capturesText}</span>
                {#if expandable}
                    <!-- A phone has no room beside Open, so the count is the control there: a 44px
                         target around a small pill, the negative margin keeping the line's height. -->
                    <button
                        type="button"
                        class="group/captures -my-3.5 inline-flex min-h-11 min-w-11 items-center rounded-full focus-visible:outline-none sm:hidden"
                        aria-expanded={expanded}
                        aria-controls={listId}
                        onclick={() => (open = !open)}
                        data-field-log-captures-phone
                    >
                        <!-- A quiet chip, not a second button shape: tinted, no border, the chevron
                             after the count so the line still reads score, then captures. -->
                        <span class="inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 font-semibold group-focus-visible/captures:ring-2 group-focus-visible/captures:ring-brand-500 {expanded
                            ? 'bg-brand-50 text-brand-700 dark:bg-brand-950/50 dark:text-brand-300'
                            : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300'}">
                            {capturesText}
                            <svg class="h-3 w-3 transition-transform duration-200 motion-reduce:transition-none {expanded ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 8 5 5 5-5" /></svg>
                        </span>
                    </button>
                {/if}
            {/if}
            {#if visit.audioConfirmed}
                <!-- A second sensor agreed; said in words, so it is never colour alone. -->
                <span class="inline-flex shrink-0 items-center gap-1 font-medium text-brand-700 dark:text-brand-300" data-field-log-audio>
                    <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                        <path stroke-linecap="round" d="M4 10v4M8 6v12M12 3v18M16 7v10M20 10v4" />
                    </svg>
                    {$_('detection.fact_heard_yes', { default: 'matching call' })}
                </span>
            {/if}
        </p>
    </div>

    {#if showCamera}
        <span class="hidden shrink-0 items-center gap-1.5 rounded-full border border-slate-200 px-2 py-0.5 text-[11px] text-slate-500 sm:inline-flex dark:border-slate-700 dark:text-slate-400" data-field-log-camera>
            <svg class="h-3 w-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <path stroke-linecap="round" stroke-linejoin="round" d="M4 8h11v8H4z" />
                <path stroke-linecap="round" stroke-linejoin="round" d="m15 12 5-3v6l-5-3z" />
            </svg>
            {visit.camera}
        </span>
    {/if}

    <span class="hidden flex-col items-end gap-1 sm:flex">
        <BadgeHint text={$_('detection.confidence_hint', { values: { score: percent(score) } })} class="rounded text-xs font-bold tabular-nums {scoreTone(score)}">{percent(score)}%</BadgeHint>
        <span class="h-[3px] w-16 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
            <span class="block h-full rounded-full {barTone(score)}" style="width: {percent(score)}%"></span>
        </span>
        {#if captureCount > 1}
            <!-- A visit's score is its best capture's, the one its photo comes from. -->
            <span class="text-[10px] text-slate-500 dark:text-slate-400" data-field-log-best-capture>{$_('visits.best_capture', { default: 'best capture' })}</span>
        {/if}
    </span>

    <span class="flex items-center justify-end gap-1">
        {#if expandable}
            <!-- The visit's open control: a real button in the same place on every row, costing no
                 height. Its label says what it does; the count says how much it holds. -->
            <button
                type="button"
                class="hidden min-h-11 min-w-11 items-center justify-center gap-1 rounded-xl border px-2 text-xs sm:inline-flex font-semibold tabular-nums transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {expanded
                    ? 'border-brand-300 bg-brand-50 text-brand-700 dark:border-brand-700 dark:bg-brand-950/40 dark:text-brand-300'
                    : 'border-slate-200 bg-white text-slate-600 hover:border-brand-300 hover:text-brand-700 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300 dark:hover:text-brand-300'}"
                aria-expanded={expanded}
                aria-controls={listId}
                aria-label={expanded
                    ? $_('visits.hide_captures', { default: 'Hide captures' })
                    : $_('visits.show_captures', { values: { count: captureCount }, default: 'Show {count} captures' })}
                title={expanded
                    ? $_('visits.hide_captures', { default: 'Hide captures' })
                    : $_('visits.show_captures', { values: { count: captureCount }, default: 'Show {count} captures' })}
                onclick={() => (open = !open)}
                data-field-log-captures-toggle
            >
                <svg class="h-3.5 w-3.5 transition-transform duration-200 motion-reduce:transition-none {expanded ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 8 5 5 5-5" /></svg>
                <span aria-hidden="true">{captureCount}</span>
            </button>
        {/if}
        {#if visit.needsReview && canIdentify}
            <button class="btn btn-primary min-h-11 px-2 py-1.5 text-xs sm:px-3" onclick={() => onidentify?.(visit.best)}>
                {$_('dashboard.field_log.identify', { default: 'Identify' })}
            </button>
        {:else}
            <!-- Opens the visit's photo record; on a phone it is an arrow so the name keeps its width. -->
            <button
                class="btn btn-ghost min-h-11 min-w-11 px-0 py-1.5 text-xs sm:px-3"
                aria-label={$_('dashboard.field_log.open_species', { values: { species: naming.primary }, default: 'Open {species}' })}
                onclick={() => onselect?.(visit.best)}
            >
                <span class="hidden sm:inline">{$_('dashboard.field_log.open', { default: 'Open' })}</span>
                <svg class="h-4 w-4 sm:hidden" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="m8 5 5 5-5 5" />
                </svg>
            </button>
        {/if}
    </span>

    {#if birds}
        {@const text = birdsText(birds)}
        <!-- Its own line, so the bird count wraps instead of truncating beside the name. The thread
             carries on beside it, and stays tinted while the captures beneath are open. -->
        <span class="relative col-start-2 flex h-full justify-center" aria-hidden="true">
            <span class="absolute inset-y-[-0.7rem] w-px bg-slate-200 dark:bg-slate-700/70"></span>
        </span>
        <div class="col-[3/-1] -mt-1 min-w-0 sm:col-[4/-1]" data-field-log-footer>
            <button
                type="button"
                class="-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-left text-xs font-medium text-slate-600 transition-colors hover:bg-slate-100 hover:text-brand-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800/60 dark:hover:text-brand-300"
                aria-label={$_('dashboard.field_log.birds_open', { values: { summary: text }, default: '{summary}, open that capture' })}
                onclick={() => onselect?.(birds.detection)}
                data-field-log-birds={birds.summary.counted}
            >
                <svg class="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M16 7h.01M3.4 18H12a8 8 0 0 0 8-8V7a4 4 0 0 0-7.28-2.3L2 20" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="m20 7 2 .5-2 .5M10 18v3M14 17.75V21" />
                </svg>
                <span class="min-w-0">{text}</span>
            </button>
        </div>
    {/if}

    {#if list && expandable}
        <ol
            id={listId}
            class="col-span-full mt-1 grid-cols-subgrid rounded-xl bg-slate-50 py-1 dark:bg-slate-800/30 {expanded ? 'grid' : 'hidden'}"
            aria-label="{naming.primary}, {capturesText}"
            aria-busy={list.loading}
            data-visit-captures={server?.visit_id}
        >
            <li class="col-span-full grid grid-cols-subgrid" data-visit-captures-caption>
                <span></span>{@render branch(null)}
                <p class="col-[3/-1] py-1 text-[11px] text-slate-500 dark:text-slate-400">
                    {$_('visits.captures_caption', { default: 'Captures in this visit, oldest first.' })}
                </p>
            </li>
            {#each list.captures as capture (capture.frigate_event)}
                {@const time = captureTime(capture)}
                {@const notes = captureNotes(capture)}
                {@const captureScore = capture.score ?? 0}
                {@const captureNaming = names(capture)}
                <li class="col-span-full grid grid-cols-subgrid items-center py-0.5" data-visit-capture={capture.frigate_event}>
                    <time class="block text-[11px] tabular-nums text-slate-500 dark:text-slate-400" datetime={capture.detection_time}>{time}</time>
                    {@render branch(
                        'capture',
                        server && captureFacts(capture, server).shown
                            ? $_('visits.node_capture_shown', { values: { time }, default: 'Capture at {time}, part of this visit, and its visit photo' })
                            : $_('visits.node_capture', { values: { time }, default: 'Capture at {time}, part of this visit' })
                    )}
                    <DetectionPreview
                        detection={capture}
                        primaryName={captureNaming.primary}
                        secondaryName={captureNaming.secondary}
                        label={$_('visits.open_capture_at', { values: { species: captureNaming.primary, time }, default: 'Open {species} capture at {time}' })}
                        onopen={() => onselect?.(capture)}
                    />
                    <div class="min-w-0 py-1">
                        <!-- Quieter than the visit above it: a capture is a moment of the visit. -->
                        <button type="button" class="block min-h-11 w-full rounded-lg text-left focus-ring" onclick={() => onselect?.(capture)}>
                            <span class="block break-words text-[13px] font-medium leading-5 text-slate-700 dark:text-slate-200">{captureNaming.primary}</span>
                            {#if captureNaming.secondary}<span class="block break-words text-[11px] italic text-slate-500 dark:text-slate-400">{captureNaming.secondary}</span>{/if}
                        </button>
                        <p class="flex min-w-0 flex-wrap items-baseline gap-x-1.5 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                            <span class="font-bold tabular-nums sm:hidden {scoreTone(captureScore)}" data-visit-capture-score>{percent(captureScore)}%</span>
                            {#each notes as note (note.text)}
                                <span class={note.emphasis ? 'font-medium text-brand-700 dark:text-brand-300' : ''}>{note.text}</span>
                            {/each}
                        </p>
                    </div>
                    {#if showCamera}<span class="hidden sm:block"></span>{/if}
                    <BadgeHint text={$_('detection.confidence_hint', { values: { score: percent(captureScore) } })} data-visit-capture-score class="hidden justify-end rounded text-xs font-bold tabular-nums sm:flex {scoreTone(captureScore)}">
                        {percent(captureScore)}%
                    </BadgeHint>
                    <span class="flex justify-end">
                        {#if onplay && capture.has_clip}
                            <button
                                type="button"
                                class="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800 dark:hover:text-brand-400"
                                aria-label={$_('detection.play_video', { values: { species: `${captureNaming.primary}, ${time}` } })}
                                onclick={() => onplay?.(capture)}
                            >
                                <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                            </button>
                        {/if}
                    </span>
                </li>
            {/each}

            {#if list.loading && list.captures.length === 0}
                {#each [0, 1] as placeholder (placeholder)}
                    <li class="col-span-full grid grid-cols-subgrid items-center py-0.5" aria-hidden="true">
                        <span class="h-2.5 w-10 rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                        {@render branch('capture')}
                        <span class="grid min-h-11 min-w-11 place-items-center">
                            <span class="h-9 w-9 rounded-lg bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60" data-loading-placeholder></span>
                        </span>
                    </li>
                {/each}
            {/if}
            {#if list.loading}
                <li class="col-span-full grid grid-cols-subgrid">
                    <span></span>{@render branch(null)}
                    <p role="status" class="col-[3/-1] py-1 text-xs text-slate-500 dark:text-slate-400 {list.captures.length === 0 ? 'sr-only' : ''}">
                        {$_('common.loading')}
                    </p>
                </li>
            {:else if list.failed}
                <li class="col-span-full grid grid-cols-subgrid">
                    <span></span>{@render branch(null)}
                    <div class="col-[3/-1] flex flex-wrap items-center gap-x-3 gap-y-1 py-1" role="alert">
                        <p class="text-xs text-slate-600 dark:text-slate-300">{$_('visits.load_failed', { default: 'Could not load the captures. Try again.' })}</p>
                        <button type="button" class="btn btn-secondary min-h-11 px-3 text-xs" onclick={() => void list.load()}>{$_('common.retry', { default: 'Retry' })}</button>
                    </div>
                </li>
            {:else if list.loaded && list.captures.length === 0}
                <li class="col-span-full grid grid-cols-subgrid">
                    <span></span>{@render branch(null)}
                    <p class="col-[3/-1] py-2 text-xs text-slate-500 dark:text-slate-400">
                        {$_('visits.captures_empty', { default: 'No captures from this visit are visible in this view.' })}
                    </p>
                </li>
            {:else if list.hasMore}
                <li class="col-span-full grid grid-cols-subgrid">
                    <span></span>{@render branch(null)}
                    <div class="col-[3/-1] flex flex-wrap items-center gap-x-3 gap-y-1 py-1">
                        <button type="button" class="btn btn-secondary min-h-11 px-3 text-xs" onclick={() => void list.load()}>
                            {$_('visits.load_more', { default: 'Load more captures' })}
                        </button>
                        <p class="text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
                            {$_('visits.loaded_of_total', { values: { shown: list.captures.length, total: list.total }, default: '{shown} of {total} captures shown' })}
                        </p>
                    </div>
                </li>
            {/if}
        </ol>
    {/if}
</li>
