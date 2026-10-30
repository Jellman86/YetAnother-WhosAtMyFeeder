<script lang="ts">
    /**
     * A Garden visit's captures, listed as a bird visit's are (`VisitCaptures`): opened from the
     * row or card, read a bounded page at a time, each capture with its own time to the second,
     * name, state and score, and each opening that exact photo in the record.
     */
    import { onDestroy, untrack } from 'svelte';
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenPhotoPreview from './GardenPhotoPreview.svelte';
    import type { GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { formatTime } from '../utils/datetime';
    import { gardenCaptureFacts, gardenEntryText, gardenEntryView, type GardenVisit } from '../utils/garden-explorer';
    import { GardenVisitCaptureList } from '../utils/garden-visit-capture-list.svelte';
    import type { GardenCaptureScope } from '../utils/garden-visit-viewer.svelte';

    interface Props {
        visit: GardenVisit;
        scope: GardenCaptureScope;
        /**
         * `footer` closes an Explorer card or row. `inline` sits inside a field log row, which
         * already states the span.
         */
        layout?: 'footer' | 'inline';
        /** Card grids float the captures above neighbouring cards without moving the grid. */
        floating?: boolean;
        onselect: (capture: GardenCapture, index: number) => void;
    }
    let { visit, scope, layout = 'footer', floating = false, onselect }: Props = $props();
    const uid = $props.id();
    const panelId = `${uid}-garden-captures`;
    let open = $state(false);
    let trigger = $state<HTMLButtonElement>();
    let panel = $state<HTMLDivElement>();
    let position = $state('');
    let failedPhotos = $state.raw<ReadonlySet<string>>(new Set());
    const list = new GardenVisitCaptureList(() => ({ visit, scope }));
    const count = $derived(visit.captureCount ?? visit.items.length);
    const inline = $derived(layout === 'inline');
    const countText = $derived($_('visits.captures', { values: { count }, default: '{count} captures' }));
    // The bird toggle's span, so a Garden stay says when it was as a bird visit does.
    const span = $derived.by((): string | null => {
        if (!visit.startTime || !visit.endTime) return null;
        const start = formatTime(visit.startTime);
        const end = formatTime(visit.endTime);
        return start === end ? start : `${start}–${end}`;
    });

    // Opening reads the first page once; the list's key alone decides when it is stale.
    $effect(() => {
        void list.key;
        if (!open) return;
        untrack(() => list.ensure());
    });
    onDestroy(() => list.dispose());

    function placePanel(): void {
        if (!trigger) return;
        const rect = trigger.getBoundingClientRect();
        const { innerWidth: width, innerHeight: height } = globalThis.window;
        const panelWidth = Math.min(420, width - 16);
        const left = Math.max(8, Math.min(rect.left, width - panelWidth - 8));
        if (width < 640) {
            position = `left:8px;bottom:8px;width:${panelWidth}px;max-height:${Math.max(0, height - 16) * 0.75}px`;
            return;
        }
        const below = height - rect.bottom - 16;
        const above = rect.top - 16;
        const flip = below < 240 && above > below;
        position = `left:${left}px;width:${panelWidth}px;max-height:${Math.max(0, Math.min(480, flip ? above : below))}px;${flip ? `bottom:${height - rect.top + 8}px` : `top:${rect.bottom + 8}px`}`;
    }

    function select(capture: GardenCapture, index: number): void {
        if (floating) panel?.hidePopover();
        onselect(capture, index);
    }

    function translate(key: string, fallback: string, values?: Record<string, string>): string {
        return get(_)(key, { values, default: fallback });
    }

    // Captures in one visit are seconds apart, so minutes alone would print the same time twice.
    function captureTime(capture: GardenCapture): string {
        return formatTime(capture.observed_at, { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function photo(capture: GardenCapture): { src: string; cropped: boolean } | null {
        const crop = capture.crop_url ? withAuthParams(capture.crop_url) : null;
        if (crop && !failedPhotos.has(crop)) return { src: crop, cropped: true };
        const whole = capture.snapshot_url ? withAuthParams(capture.snapshot_url) : null;
        return whole && !failedPhotos.has(whole) ? { src: whole, cropped: false } : null;
    }

    function scoreTone(score: number, needsReview: boolean): string {
        if (needsReview) return 'text-amber-800 dark:text-amber-300';
        if (score < 0.85) return 'text-brand-700 dark:text-brand-300';
        return 'text-success-700 dark:text-success-300';
    }
</script>

{#if count > 1}
    <div class="min-w-0 {inline ? '' : 'border-t border-slate-200/80 dark:border-slate-700/60'}" data-garden-visit-captures={visit.id}>
        <button
            type="button"
            bind:this={trigger}
            popovertarget={floating ? panelId : undefined}
            class={inline
                ? '-ml-2 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-100 hover:text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800/60 dark:hover:text-white'
                : 'flex min-h-11 w-full items-center gap-2 px-4 py-2 text-left text-xs font-semibold text-slate-600 transition-colors hover:bg-slate-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:text-slate-300 dark:hover:bg-slate-800/50'}
            aria-expanded={open}
            aria-controls={panelId}
            onclick={() => { if (!floating) open = !open; }}
            data-garden-visit-captures-toggle
        >
            <svg class="h-3.5 w-3.5 shrink-0 text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true">
                <rect x="3" y="7" width="13" height="13" rx="2" />
                <path stroke-linecap="round" stroke-linejoin="round" d="M8 4h11a2 2 0 0 1 2 2v11" />
            </svg>
            <span class="min-w-0 {inline ? '' : 'flex-1'}">
                <span>{countText}</span>
                {#if !inline && span}<span class="font-normal tabular-nums text-slate-500 dark:text-slate-400" data-garden-visit-captures-span>&middot; {span}</span>{/if}
            </span>
            <svg class="h-3.5 w-3.5 shrink-0 transition-transform duration-200 motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                <path d="m5 7 5 5 5-5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
        </button>

        <div
            bind:this={panel}
            id={panelId}
            popover={floating ? 'auto' : undefined}
            hidden={!floating && !open}
            onbeforetoggle={(event) => { if (floating && event.newState === 'open') placePanel(); }}
            ontoggle={(event) => { if (floating) open = event.newState === 'open'; }}
            role={floating ? 'region' : undefined}
            aria-label={floating ? countText : undefined}
            aria-busy={list.loading}
            data-garden-visit-captures-floating={floating ? '' : undefined}
            style={floating ? position : undefined}
            class={floating ? 'fixed inset-auto m-0 overflow-y-auto overscroll-contain rounded-2xl border border-slate-200 bg-white pb-2 text-slate-900 shadow-xl dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100' : inline ? 'pb-1' : 'pb-2'}
        >
            {#if floating}
                <div class="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-slate-200 bg-white px-4 py-1 dark:border-slate-700 dark:bg-slate-900">
                    <p class="text-sm font-semibold">{countText}</p>
                    <button type="button" class="btn btn-ghost min-h-11 min-w-11 px-2" popovertarget={panelId} popovertargetaction="hide">{$_('common.close', { default: 'Close' })}</button>
                </div>
            {/if}
            <p class="py-1 text-2xs text-slate-500 dark:text-slate-400 {inline ? '' : 'px-4'}">
                {$_('garden.explorer.capture_actions', { default: 'Open a capture to review it on its own photo.' })}
            </p>

            {#if list.captures.length > 0}
                <ol class={inline ? '' : 'border-y border-slate-200/70 dark:border-slate-700/50'}>
                    {#each list.captures as capture, index (capture.id)}
                        {@const view = gardenEntryView(capture)}
                        {@const text = gardenEntryText(capture, view, translate)}
                        {@const facts = gardenCaptureFacts(capture, visit)}
                        {@const time = captureTime(capture)}
                        {@const image = photo(capture)}
                        <li
                            class="relative grid grid-cols-[auto_minmax(0,1fr)_auto] items-center gap-x-2.5 {inline ? '' : 'border-b border-slate-200/70 px-3 last:border-b-0 dark:border-slate-700/50'}"
                            data-garden-visit-capture={capture.id}
                        >
                            <!-- The whole line opens the exact capture, so a thumb lands anywhere along it. -->
                            <button
                                type="button"
                                class="absolute inset-0 z-0 rounded-lg transition-colors hover:bg-slate-100/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:hover:bg-slate-800/50"
                                aria-label={$_('visits.open_capture_at', { values: { species: text.title, time }, default: 'Open {species} capture at {time}' })}
                                onclick={() => select(capture, index)}
                            ></button>
                            <span class="pointer-events-none relative z-10 grid min-h-11 min-w-11 place-items-center" aria-hidden="true">
                                <span class="block h-9 w-9 overflow-hidden rounded-lg border-2 border-white bg-slate-100 dark:border-slate-900 dark:bg-slate-800">
                                    {#if image}
                                        <GardenPhotoPreview {capture} src={image.src} cropped={image.cropped} aspect={1}
                                            onerror={() => (failedPhotos = new Set([...failedPhotos, image.src]))} />
                                    {/if}
                                </span>
                            </span>
                            <div class="pointer-events-none relative z-10 min-w-0 py-1">
                                <p class="break-words text-sm font-semibold leading-5 text-slate-800 dark:text-slate-100">{text.title}</p>
                                {#if capture.scientific_name && capture.scientific_name !== text.title}<p class="break-words text-xs italic text-slate-500 dark:text-slate-400">{capture.scientific_name}</p>{/if}
                                <time class="block text-xs font-semibold tabular-nums text-slate-800 dark:text-slate-100" datetime={capture.observed_at}>{time}</time>
                                <p class="flex flex-wrap items-baseline gap-x-1.5 text-2xs leading-4 text-slate-500 dark:text-slate-400" data-garden-visit-capture-notes>
                                    {#if facts.shown}
                                        <span class="font-medium text-brand-700 dark:text-brand-300">{$_('visits.shown_photo', { default: 'Visit photo' })}</span>
                                        <span aria-hidden="true">&middot;</span>
                                    {/if}
                                    <span class={facts.review ? 'font-medium text-amber-800 dark:text-amber-300' : ''}>{text.state}</span>
                                    {#if facts.motion}
                                        <span aria-hidden="true">&middot;</span>
                                        <span>{$_('garden.explorer.capture_motion', { default: 'Motion footage' })}</span>
                                    {/if}
                                </p>
                            </div>
                            <div class="pointer-events-none relative z-10 min-w-10 text-right">
                                {#if view.score !== null}
                                    <span class="text-xs font-bold tabular-nums {scoreTone(view.score, Boolean(view.review))}">{Math.round(view.score * 100)}%</span>
                                {/if}
                            </div>
                        </li>
                    {/each}
                </ol>
            {:else if list.loading}
                <div class="space-y-1 {inline ? '' : 'px-3'}" aria-hidden="true">
                    {#each [0, 1] as placeholder (placeholder)}
                        <div class="h-11 animate-pulse rounded-lg bg-slate-100 motion-reduce:animate-none dark:bg-slate-800/60"></div>
                    {/each}
                </div>
            {:else if list.loaded && !list.failed}
                <p class="py-2 text-xs text-slate-500 dark:text-slate-400 {inline ? '' : 'px-4'}">
                    {$_('visits.captures_empty', { default: 'No captures from this visit are visible in this view.' })}
                </p>
            {/if}

            {#if list.loading}
                <p role="status" class="py-2 text-xs text-slate-500 dark:text-slate-400 {inline ? '' : 'px-4'} {list.captures.length === 0 ? 'sr-only' : ''}">
                    {$_('common.loading')}
                </p>
            {/if}
            {#if list.failed}
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1 py-2 {inline ? '' : 'px-4'}" role="alert">
                    <p class="text-xs text-slate-600 dark:text-slate-300">{$_('visits.load_failed', { default: 'Could not load the captures. Try again.' })}</p>
                    <button type="button" class="btn btn-secondary min-h-11 px-3 text-xs" onclick={() => void list.load()}>{$_('common.retry', { default: 'Retry' })}</button>
                </div>
            {:else if list.hasMore && !list.loading}
                <div class="flex flex-wrap items-center gap-x-3 gap-y-1 pt-2 {inline ? '' : 'px-4'}">
                    <button type="button" class="btn btn-secondary min-h-11 px-3 text-xs" onclick={() => void list.load()}>
                        {$_('visits.load_more', { default: 'Load more captures' })}
                    </button>
                    <p class="text-2xs tabular-nums text-slate-500 dark:text-slate-400">
                        {$_('visits.loaded_of_total', { values: { shown: list.captures.length, total: list.total }, default: '{shown} of {total} captures shown' })}
                    </p>
                </div>
            {/if}
        </div>
    </div>
{/if}
