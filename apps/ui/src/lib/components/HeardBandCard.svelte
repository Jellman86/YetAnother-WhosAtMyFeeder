<script lang="ts">
    /**
     * The calls heard between two visits, as one tile in the Explorer's card grid.
     *
     * The picture is the spectrograms of its busiest species beside the number of calls, so the
     * tile never borrows a photograph it does not have. Its calls open over the grid, like a
     * visit's captures, without moving any card.
     */
    import { _ } from 'svelte-i18n';
    import HeardBandHeading from './HeardBandHeading.svelte';
    import HeardCallList from './HeardCallList.svelte';
    import type { HeardBand } from '../utils/heard-timeline';
    import { withAuthParams } from '../api/core';
    import { appApiPath } from '../app/url-base';
    import { relativeDayLabel } from '../utils/day-label';
    import { formatTime } from '../utils/datetime';
    import { heardSpanEnds } from '../utils/heard-labels';

    interface Props {
        band: HeardBand;
    }
    let { band }: Props = $props();
    const uid = $props.id();
    const panelId = `${uid}-calls`;
    let open = $state(false);
    let trigger = $state<HTMLButtonElement>();
    let panel = $state<HTMLDivElement>();
    let position = $state('');
    let failed = $state<Record<number, true>>({});

    const pictures = $derived(band.pictures.filter((id) => !failed[id]).slice(0, 3));
    const span = $derived.by(() => {
        const { from, to } = heardSpanEnds(band.firstHeard, band.lastHeard, (value) => relativeDayLabel(value, $_));
        return from === to ? from : $_('events.heard.time_span', { values: { from, to }, default: '{from} to {to}' });
    });

    function spectrogram(id: number): string {
        return withAuthParams(`${appApiPath(`/audio/spectrogram/${id}`)}?width=300`);
    }

    function placePanel(): void {
        if (!trigger) return;
        const rect = trigger.getBoundingClientRect();
        const { innerWidth: width, innerHeight: height } = window;
        const panelWidth = Math.min(440, width - 16);
        if (width < 640) {
            position = `left:8px;bottom:8px;width:${panelWidth}px;max-height:${Math.max(0, height - 16) * 0.75}px`;
            return;
        }
        const left = Math.max(8, Math.min(rect.left, width - panelWidth - 8));
        const below = height - rect.bottom - 16;
        const above = rect.top - 16;
        const flip = below < 240 && above > below;
        position = `left:${left}px;width:${panelWidth}px;max-height:${Math.max(0, Math.min(520, flip ? above : below))}px;${flip ? `bottom:${height - rect.top + 8}px` : `top:${rect.bottom + 8}px`}`;
    }

    $effect(() => {
        if (!open) return;
        const reposition = (event: Event): void => {
            if (event.target instanceof Node && panel?.contains(event.target)) return;
            placePanel();
        };
        window.addEventListener('resize', reposition);
        window.addEventListener('scroll', reposition, true);
        return () => {
            window.removeEventListener('resize', reposition);
            window.removeEventListener('scroll', reposition, true);
        };
    });
</script>

<article
    class="flex h-full flex-col overflow-hidden rounded-2xl border border-dashed border-line bg-surface-raised/40"
    data-heard-band-card={band.position}
>
    <div class="relative aspect-[4/3] overflow-hidden bg-slate-200 dark:bg-slate-950" aria-hidden="true">
        <div class="grid h-full grid-cols-2 grid-rows-2 gap-0.5">
            {#each pictures as id (id)}
                <span class="block overflow-hidden bg-slate-100 dark:bg-slate-900 {pictures.length === 1 ? 'row-span-2' : ''}">
                    <img src={spectrogram(id)} alt="" loading="lazy" class="h-full w-full scale-125 object-cover [transform-origin:50%_64%]" onerror={() => (failed = { ...failed, [id]: true })} />
                </span>
            {/each}
            <span class="flex flex-col items-center justify-center bg-surface text-slate-700 dark:text-slate-200 {pictures.length === 0 ? 'col-span-2 row-span-2' : pictures.length === 1 ? 'row-span-2' : pictures.length === 2 ? 'col-span-2' : ''}">
                <span class="font-display text-lg font-bold tabular-nums">{$_('events.heard.calls', { values: { count: band.callCount }, default: '{count} calls' })}</span>
            </span>
        </div>
        <span class="absolute bottom-3 left-3 inline-flex min-h-11 items-center gap-1.5 rounded-full border border-white/10 bg-black/60 px-3 text-xs font-bold text-white backdrop-blur-md">
            <svg class="h-3 w-3 text-brand-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" /></svg>
            <!-- Like a visit card, the photo pill gives when it began; the heading gives the span. -->
            <time datetime={band.firstHeard}>{formatTime(band.firstHeard)}</time>
        </span>
    </div>
    <div class="flex flex-1 flex-col gap-2 p-4">
        <HeardBandHeading {band} maxSpecies={4} />
        <button
            type="button"
            bind:this={trigger}
            popovertarget={panelId}
            class="mt-auto inline-flex min-h-11 items-center gap-1.5 self-start rounded-lg px-2 -ml-2 text-xs font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:bg-brand-500/10"
            aria-expanded={open}
            aria-controls={panelId}
            data-heard-band-toggle
        >
            {$_('events.heard.show_calls', { default: 'Show calls' })}
            <svg class="h-3.5 w-3.5" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true"><path d="m5 7 5 5 5-5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" /></svg>
        </button>
    </div>
    <div
        bind:this={panel}
        id={panelId}
        popover="auto"
        onbeforetoggle={(event) => { if (event.newState === 'open') placePanel(); }}
        ontoggle={(event) => (open = event.newState === 'open')}
        role="region"
        aria-label={$_('events.heard.calls_panel', { default: 'Heard calls' })}
        style={position}
        class="fixed inset-auto m-0 overflow-y-auto overscroll-contain rounded-2xl border border-line bg-surface pb-2 text-slate-900 shadow-xl dark:text-slate-100"
    >
        <div class="sticky top-0 z-20 flex items-center justify-between gap-3 border-b border-line-soft bg-surface px-4 py-1">
            <p class="text-sm font-semibold">{$_('events.heard.calls_panel', { default: 'Heard calls' })}<span class="ml-2 text-xs font-normal tabular-nums text-slate-500 dark:text-slate-400">{span}</span></p>
            <button type="button" class="btn btn-ghost min-h-11 min-w-11 px-2" popovertarget={panelId} popovertargetaction="hide">{$_('common.close', { default: 'Close' })}</button>
        </div>
        {#if open}<HeardCallList groups={band.groups} inline={false} />{/if}
    </div>
</article>
