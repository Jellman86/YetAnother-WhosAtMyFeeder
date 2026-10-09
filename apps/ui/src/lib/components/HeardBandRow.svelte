<script lang="ts">
    /**
     * The calls heard between two visits, as one Explorer row.
     *
     * It reads like a visit row (time, picture, subject, then the action) so the list keeps one
     * shape, and it is quieter than a visit, because the visit is what the cameras saw. Several
     * calls show as layered spectrograms, the same layering a capture with several birds uses.
     */
    import { _ } from 'svelte-i18n';
    import HeardBandHeading from './HeardBandHeading.svelte';
    import HeardCallList from './HeardCallList.svelte';
    import LayeredThumbs from './LayeredThumbs.svelte';
    import type { HeardBand } from '../utils/heard-timeline';
    import { withAuthParams } from '../api/core';
    import { appApiPath } from '../app/url-base';
    import { formatTime } from '../utils/datetime';
    import { relativeDayLabel } from '../utils/day-label';

    interface Props {
        band: HeardBand;
    }
    let { band }: Props = $props();
    const uid = $props.id();
    let open = $state(false);

    const pictures = $derived(band.pictures.slice(0, 2).map((id) => withAuthParams(`${appApiPath(`/audio/spectrogram/${id}`)}?width=200`)));
    const day = $derived(relativeDayLabel(band.firstHeard, $_));
</script>

<div class="border-t border-slate-200 bg-slate-50/80 first:border-t-0 dark:border-slate-800 dark:bg-slate-950/40" data-heard-band={band.position}>
    <div class="grid grid-cols-[3.25rem_2.75rem_minmax(0,1fr)] items-start gap-3 px-3 py-2">
        <div class="pt-0.5">
            <!-- Like a visit row, a band is placed and labelled by when it began. -->
            <time class="block font-display text-sm font-bold tabular-nums leading-tight text-slate-600 dark:text-slate-300" datetime={band.firstHeard}>{formatTime(band.firstHeard)}</time>
            {#if day}<span class="block text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">{day}</span>{/if}
        </div>
        <LayeredThumbs sources={pictures} spectrogram />
        <div class="min-w-0">
            <HeardBandHeading {band} />
            <button
                type="button"
                class="-ml-2 mt-0.5 inline-flex min-h-11 items-center gap-1.5 rounded-lg px-2 text-xs font-semibold text-brand-700 transition-colors hover:bg-brand-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:text-brand-300 dark:hover:bg-brand-500/10"
                aria-expanded={open}
                aria-controls="{uid}-calls"
                onclick={() => (open = !open)}
                data-heard-band-toggle
            >
                {open ? $_('events.heard.hide_calls', { default: 'Hide calls' }) : $_('events.heard.show_calls', { default: 'Show calls' })}
                <svg class="h-3.5 w-3.5 transition-transform duration-200 motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                    <path d="m5 7 5 5 5-5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                </svg>
            </button>
        </div>
    </div>
    <div id="{uid}-calls" hidden={!open} class="border-t border-slate-200/70 dark:border-slate-800/80">
        {#if open}<HeardCallList groups={band.groups} />{/if}
    </div>
</div>
