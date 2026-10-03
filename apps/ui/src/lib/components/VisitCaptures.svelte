<script lang="ts">
    import { onDestroy, untrack, type Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import DetectionPreview from './DetectionPreview.svelte';
    import type { DetectionVisit, VisitOptions } from '../api/visits';
    import { settingsStore } from '../stores/settings.svelte';
    import { VisitCaptureList } from '../utils/visit-capture-list.svelte';
    import { getBirdNames } from '../naming';
    import { formatTime } from '../utils/datetime';
    import { captureFacts, hasCaptureTimeline, type CaptureFacts } from '../utils/visit-captures';
    import type { Detection } from '../api';

    interface Props {
        visit: DetectionVisit;
        window?: VisitOptions;
        /**
         * `footer` closes an Explorer card or row and states the span and busiest capture itself.
         * `inline` sits inside a log row that already states both, and continues its thread.
         */
        layout?: 'footer' | 'inline';
        /** Inline context beside the toggle, such as the field log's busiest-capture count. */
        aside?: Snippet;
        onselect?: (detection: Detection) => void;
        onplay?: (detection: Detection) => void;
    }
    let { visit, window = {}, layout = 'footer', aside, onselect, onplay }: Props = $props();
    const uid = $props.id();
    const panelId = `${uid}-captures`;
    let open = $state(false);
    const list = new VisitCaptureList(() => ({ visit, window }));
    const captures = $derived(list.captures);
    const total = $derived(list.total);
    const loaded = $derived(list.loaded);
    const loading = $derived(list.loading);
    const error = $derived(list.failed);
    const span = $derived.by(() => {
        const start = formatTime(visit.start_time);
        const end = formatTime(visit.end_time);
        return start === end ? start : `${start}–${end}`;
    });
    const peak = $derived(visit.peak_capture?.bird_summary?.counted ?? null);
    const inline = $derived(layout === 'inline');

    // Opening reads the first page once; the membership key alone decides when it is stale.
    $effect(() => {
        void list.key;
        if (!open) return;
        untrack(() => list.ensure());
    });
    onDestroy(() => list.dispose());

    function names(capture: Detection): { primary: string; secondary: string | null } {
        return getBirdNames(capture, settingsStore.displayCommonNames, settingsStore.scientificNamePrimary);
    }

    // Captures in one visit are seconds apart, so minutes alone would print the same time twice.
    function captureTime(capture: Detection): string {
        return formatTime(capture.detection_time, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function notes(facts: CaptureFacts): { text: string; emphasis: boolean }[] {
        const found: { text: string; emphasis: boolean }[] = [];
        if (facts.shown) found.push({ text: $_('visits.shown_photo', { default: 'Visit photo' }), emphasis: true });
        if (facts.birds !== null) {
            found.push({ text: $_('visits.capture_birds', { values: { count: facts.birds }, default: '{count} birds' }), emphasis: false });
        }
        if (facts.heard) found.push({ text: $_('detection.fact_heard_yes', { default: 'matching call' }), emphasis: true });
        return found;
    }

    /** The bands the visual standard sets: under 60 amber, under 85 brand, above green. */
    function scoreTone(score: number): string {
        if (score < 0.6) return 'text-accent-700 dark:text-accent-300';
        if (score < 0.85) return 'text-brand-700 dark:text-brand-300';
        return 'text-success-700 dark:text-success-300';
    }
</script>

{#if hasCaptureTimeline(visit)}
    <div
        class="min-w-0 {inline ? '' : 'border-t border-slate-200/80 dark:border-slate-700/60'}"
        data-visit-captures={visit.visit_id}
        data-visit-captures-open={open ? '' : undefined}
    >
        <div class="flex flex-wrap items-center gap-x-1">
            <button
                type="button"
                class={inline
                    ? '-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800/60 dark:hover:text-white'
                    : 'flex min-h-11 w-full items-center gap-2 px-4 py-2 text-left text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800/50'}
                aria-expanded={open}
                aria-controls={panelId}
                onclick={() => (open = !open)}
                data-visit-captures-toggle
            >
                <svg class="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                    <rect x="3" y="7" width="13" height="13" rx="2" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M8 4h11a2 2 0 0 1 2 2v11" />
                </svg>
                <span class="min-w-0 {inline ? '' : 'flex-1'}">
                    <span>{$_('visits.captures', { values: { count: visit.capture_count }, default: '{count} captures' })}</span>
                    {#if !inline}
                        <span class="font-normal tabular-nums text-slate-500 dark:text-slate-400">&middot; {span}</span>
                        {#if peak !== null && peak >= 2}
                            <span class="block font-medium text-slate-500 dark:text-slate-400">
                                {$_('visits.peak_birds', { values: { count: peak }, default: '{count} birds in one capture' })}
                            </span>
                        {/if}
                    {/if}
                </span>
                <svg class="h-3.5 w-3.5 shrink-0 transition-transform duration-200 motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                    <path d="m5 7 5 5 5-5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
            </button>
            {@render aside?.()}
        </div>

        <div id={panelId} hidden={!open} aria-busy={loading} class={inline ? 'pb-1' : 'pb-2'}>
            <p class="py-1 text-[11px] text-slate-500 dark:text-slate-400 {inline ? '' : 'px-4'}">
                {$_('visits.capture_actions', { default: 'Open a capture to review its identification or play its clip.' })}
            </p>

            {#if captures.length > 0}
                <ol class={inline ? '' : 'border-y border-slate-200/70 dark:border-slate-700/50'}>
                    {#each captures as capture (capture.frigate_event)}
                        {@const naming = names(capture)}
                        {@const time = captureTime(capture)}
                        {@const facts = captureFacts(capture, visit)}
                        {@const captureNotes = notes(facts)}
                        {@const score = capture.score ?? 0}
                        <li
                            class="relative grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2 {inline
                                ? 'sm:grid-cols-[0.75rem_auto_minmax(0,1fr)_auto] sm:gap-x-2.5'
                                : 'border-b border-slate-200/70 px-3 last:border-b-0 dark:border-slate-700/50'}"
                            data-visit-capture={capture.frigate_event}
                        >
                            <!-- The whole line opens the exact capture, so a thumb lands anywhere along it. -->
                            <button
                                type="button"
                                class="absolute inset-0 z-0 rounded-lg transition-colors hover:bg-slate-100/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:hover:bg-slate-800/50"
                                aria-label={$_('visits.open_capture_at', {
                                    values: { species: naming.primary, time },
                                    default: 'Open {species} capture at {time}'
                                })}
                                onclick={() => onselect?.(capture)}
                            ></button>

                            {#if inline}
                                <!-- A branch of the log's thread: one tick per capture, the visit photo in brand.
                                     Phones drop it, because the time needs that width more. -->
                                <span class="pointer-events-none relative hidden h-full justify-center sm:flex" aria-hidden="true">
                                    <span class="absolute inset-y-0 w-px bg-slate-200 dark:bg-slate-700/70"></span>
                                    <span class="relative my-auto h-1.5 w-1.5 rounded-full {facts.shown
                                        ? 'bg-brand-500'
                                        : 'bg-slate-300 dark:bg-slate-600'}"></span>
                                </span>
                            {/if}

                            <div class="relative z-10">
                                <DetectionPreview
                                    detection={capture}
                                    primaryName={naming.primary}
                                    secondaryName={naming.secondary}
                                    onopen={() => onselect?.(capture)}
                                />
                            </div>

                            <div class="pointer-events-none relative z-10 min-w-0 py-1">
                                <time class="block text-xs font-semibold tabular-nums text-slate-800 dark:text-slate-100" datetime={capture.detection_time}>
                                    {time}
                                </time>
                                {#if captureNotes.length > 0}
                                    <p class="flex flex-wrap items-baseline gap-x-1.5 text-[11px] leading-4 text-slate-500 dark:text-slate-400">
                                        {#each captureNotes as note, index (note.text)}
                                            {#if index > 0}<span aria-hidden="true">&middot;</span>{/if}
                                            <span class={note.emphasis ? 'font-medium text-brand-700 dark:text-brand-300' : ''}>{note.text}</span>
                                        {/each}
                                    </p>
                                {/if}
                            </div>

                            <div class="relative z-10 flex items-center gap-1">
                                {#if onplay && capture.has_clip}
                                    <button
                                        type="button"
                                        class="inline-flex h-11 w-11 items-center justify-center rounded-full text-slate-400 transition-colors hover:bg-slate-100 hover:text-brand-600 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800 dark:hover:text-brand-400"
                                        aria-label={$_('detection.play_video', { values: { species: `${naming.primary}, ${time}` } })}
                                        onclick={() => onplay?.(capture)}
                                    >
                                        <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                                            <path d="M8 5v14l11-7z" />
                                        </svg>
                                    </button>
                                {/if}
                                <span class="pointer-events-none min-w-10 text-right text-xs font-bold tabular-nums {scoreTone(score)}">
                                    {Math.round(score * 100)}%
                                </span>
                            </div>
                        </li>
                    {/each}
                </ol>
            {:else if loading}
                <div class="space-y-1 {inline ? '' : 'px-3'}" aria-hidden="true">
                    {#each [0, 1] as placeholder (placeholder)}
                        <div class="h-11 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none dark:bg-slate-800/60"></div>
                    {/each}
                </div>
            {:else if loaded && !error}
                <p class="py-2 text-xs text-slate-500 dark:text-slate-400 {inline ? '' : 'px-4'}">
                    {$_('visits.captures_empty', { default: 'No captures from this visit are visible in this view.' })}
                </p>
            {/if}

            {#if loading}
                <p role="status" class="py-2 text-xs text-slate-500 dark:text-slate-400 {inline ? '' : 'px-4'} {captures.length === 0 ? 'sr-only' : ''}">
                    {$_('common.loading')}
                </p>
            {/if}
            {#if error}
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 {inline ? '' : 'px-4'}" role="alert">
                    <p class="text-xs text-slate-600 dark:text-slate-300">{$_('visits.load_failed', { default: 'Could not load the captures. Try again.' })}</p>
                    <button type="button" class="btn btn-secondary min-h-11 px-3 text-xs" onclick={() => void list.load()}>{$_('common.retry', { default: 'Retry' })}</button>
                </div>
            {:else if captures.length > 0 && captures.length < total && !loading}
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 {inline ? '' : 'px-4'}">
                    <button type="button" class="btn btn-secondary min-h-11 px-3 text-xs" onclick={() => void list.load()}>
                        {$_('visits.load_more', { default: 'Load more captures' })}
                    </button>
                    <p class="text-[11px] tabular-nums text-slate-500 dark:text-slate-400">
                        {$_('visits.loaded_of_total', { values: { shown: captures.length, total }, default: '{shown} of {total} captures shown' })}
                    </p>
                </div>
            {/if}
        </div>
    </div>
{:else if aside}
    {@render aside()}
{:else if !inline && peak !== null && peak >= 2}
    <p class="border-t border-slate-200/80 px-4 py-3 text-xs font-medium text-slate-500 dark:border-slate-700/60 dark:text-slate-400" data-visit-captures-peak>
        {$_('visits.peak_birds', { values: { count: peak }, default: '{count} birds in one capture' })}
    </p>
{/if}
