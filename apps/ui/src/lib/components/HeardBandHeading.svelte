<script lang="ts">
    /** What a heard band says about itself: where it sits, its span, and its species with counts. */
    import { _ } from 'svelte-i18n';
    import type { HeardBand } from '../utils/heard-timeline';
    import { relativeDayLabel } from '../utils/day-label';
    import { heardSpanEnds } from '../utils/heard-labels';

    interface Props {
        band: HeardBand;
        /** Cards have less width, so they keep the busiest species and count the rest. */
        maxSpecies?: number;
    }
    let { band, maxSpecies = Infinity }: Props = $props();

    const title = $derived(
        band.position === 'after-last'
            ? $_('events.heard.after_last', { default: 'Heard after the last visit' })
            : band.position === 'before-first'
              ? $_('events.heard.before_first', { default: 'Heard before the first visit' })
              : $_('events.heard.between', { default: 'Heard between visits' })
    );
    const ends = $derived(heardSpanEnds(band.firstHeard, band.lastHeard, (value) => relativeDayLabel(value, $_)));
    const from = $derived(ends.from);
    const to = $derived(ends.to);
    const shown = $derived(band.species.slice(0, maxSpecies));
    const more = $derived(band.species.length - shown.length);
</script>

<p class="flex min-w-0 flex-wrap items-baseline gap-x-1.5 text-xs font-bold text-slate-700 dark:text-slate-200">
    <svg class="h-3.5 w-3.5 shrink-0 self-center text-brand-600 dark:text-brand-300" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" />
    </svg>
    <span>{title}</span>
    <span class="font-semibold tabular-nums text-slate-500 dark:text-slate-400">
        {from === to
            ? $_('events.heard.summary_at', { values: { time: from, calls: band.callCount, species: band.species.length }, default: '{time}, {calls} calls, {species} species' })
            : $_('events.heard.summary_span', { values: { from, to, calls: band.callCount, species: band.species.length }, default: '{from} to {to}, {calls} calls, {species} species' })}
    </span>
</p>
<ul class="mt-1.5 flex flex-wrap gap-1.5" aria-label={$_('events.heard.species_list', { default: 'Species heard' })}>
    {#each shown as entry (entry.name)}
        <li class="inline-flex min-h-6 items-center gap-1.5 rounded-full border border-line-soft bg-surface px-2 text-2xs font-semibold text-slate-700 dark:text-slate-200">
            {entry.name}<span class="font-bold tabular-nums text-brand-700 dark:text-brand-300">{entry.count}</span>
        </li>
    {/each}
    {#if more > 0}
        <li class="inline-flex min-h-6 items-center px-1 text-2xs font-semibold text-slate-500 dark:text-slate-400">
            {$_('events.heard.more_species', { values: { count: more }, default: '+{count} more' })}
        </li>
    {/if}
</ul>
