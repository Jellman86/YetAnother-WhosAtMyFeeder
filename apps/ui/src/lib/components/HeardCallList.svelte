<script lang="ts">
    /**
     * The calls inside one heard band, one line per species group, newest first.
     *
     * A line opens to the strongest call at a size worth reading: its spectrogram, the clip and,
     * for the owner, a link to the detection in BirdNET-Go. Small spectrograms are zoomed onto the
     * band where birdsong sits, because the top quarter of every BirdNET-Go spectrogram is silence.
     */
    import { _ } from 'svelte-i18n';
    import type { HeardGroup } from '../api/audio';
    import { withAuthParams } from '../api/core';
    import { appApiPath } from '../app/url-base';
    import { settingsStore } from '../stores/settings.svelte';
    import { formatTime } from '../utils/datetime';
    import { relativeDayLabel } from '../utils/day-label';
    import { heardCallsUntil, heardConfidenceTone } from '../utils/heard-labels';

    interface Props {
        groups: HeardGroup[];
        /** A floating panel keeps its own padding; an inline list lines up with the rows above it. */
        inline?: boolean;
    }
    let { groups, inline = true }: Props = $props();
    const uid = $props.id();
    let openKey = $state<string | null>(null);
    let failed = $state<Record<number, true>>({});

    const birdnetBase = $derived((settingsStore.settings?.birdnet_external_url || settingsStore.settings?.birdnet_url || '').replace(/\/$/, ''));

    // A band can run overnight; each line names its day once the day differs from the newest line's.
    const newestDay = $derived(groups.length ? new Date(groups[0].first_heard).toDateString() : '');

    function keyOf(group: HeardGroup): string {
        return `${group.scientific_name ?? group.species}:${group.first_heard}`;
    }

    function spectrogram(id: number, width: number): string {
        return withAuthParams(`${appApiPath(`/audio/spectrogram/${id}`)}?width=${width}`);
    }

    function clip(id: number): string {
        return withAuthParams(appApiPath(`/audio/clip/${id}`));
    }
</script>

<ol class="divide-y divide-slate-200/70 dark:divide-slate-800/80" data-heard-call-list>
    {#each groups as group (keyOf(group))}
        {@const key = keyOf(group)}
        {@const open = openKey === key}
        {@const picture = group.best_birdnet_id && !failed[group.best_birdnet_id] ? group.best_birdnet_id : null}
        {@const score = Math.round(group.best_confidence * 100)}
        <li data-heard-call={key}>
            <button
                type="button"
                class="grid min-h-12 w-full grid-cols-[3.25rem_2.25rem_minmax(0,1fr)_auto] items-center gap-3 py-1 text-left transition-colors hover:bg-slate-100/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500 dark:hover:bg-slate-800/50 {inline ? 'pl-3 pr-3 sm:pl-16' : 'px-3'}"
                aria-expanded={open}
                aria-controls="{uid}-{key}"
                onclick={() => (openKey = open ? null : key)}
            >
                <span>
                    <time class="block text-xs font-semibold tabular-nums text-slate-600 dark:text-slate-300" datetime={group.first_heard}>{formatTime(group.first_heard)}</time>
                    {#if new Date(group.first_heard).toDateString() !== newestDay}
                        <span class="block text-[10px] font-semibold uppercase tracking-wide text-slate-400 dark:text-slate-500">{relativeDayLabel(group.first_heard, $_)}</span>
                    {/if}
                </span>
                <span class="block h-9 w-9 overflow-hidden rounded-md bg-slate-100 ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700" aria-hidden="true">
                    {#if picture}
                        <img
                            src={spectrogram(picture, 200)}
                            alt=""
                            loading="lazy"
                            class="h-full w-full scale-[1.6] object-cover [transform-origin:50%_64%]"
                            onerror={() => (failed = { ...failed, [picture]: true })}
                        />
                    {:else}
                        <svg class="m-2 h-5 w-5 text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" /></svg>
                    {/if}
                </span>
                <span class="min-w-0">
                    <span class="block truncate text-sm font-semibold text-slate-800 dark:text-slate-100">{group.species}</span>
                    <span class="block truncate text-[11px] font-semibold text-slate-500 dark:text-slate-400">
                        {#if heardCallsUntil(group)}{$_('events.heard.calls_until', { values: { count: group.call_count, time: heardCallsUntil(group) }, default: '{count} calls to {time}' })}{:else}{$_('events.heard.calls', { values: { count: group.call_count }, default: '{count} calls' })}{/if}{#if group.source_name}{' · '}{group.source_name}{/if}
                    </span>
                </span>
                <span class="flex items-center gap-2">
                    <span class="min-w-10 text-right text-xs font-bold tabular-nums {heardConfidenceTone(group.best_confidence)}">{score}%</span>
                    <svg class="h-3.5 w-3.5 shrink-0 text-slate-400 transition-transform duration-200 motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true">
                        <path d="m5 7 5 5 5-5" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" />
                    </svg>
                </span>
            </button>
            <div id="{uid}-{key}" hidden={!open} class="pb-3 {inline ? 'px-3 sm:pl-16' : 'px-3'}">
                {#if open}
                    <div class="grid gap-3 sm:grid-cols-[minmax(0,22rem)_minmax(0,1fr)] sm:items-start">
                        <div class="aspect-[4/3] w-full overflow-hidden rounded-xl bg-slate-100 ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700">
                            {#if picture}
                                <img
                                    src={spectrogram(picture, 600)}
                                    alt={$_('events.heard.spectrogram_alt', { values: { species: group.species, time: formatTime(group.best_heard) }, default: 'Spectrogram of the strongest {species} call, {time}' })}
                                    class="h-full w-full object-cover"
                                    onerror={() => (failed = { ...failed, [picture]: true })}
                                />
                            {:else}
                                <p class="flex h-full items-center justify-center px-4 text-center text-xs text-slate-500 dark:text-slate-400">
                                    {$_('events.heard.no_spectrogram', { default: 'BirdNET-Go has no spectrogram for these calls any more.' })}
                                </p>
                            {/if}
                        </div>
                        <div class="space-y-2 text-xs text-slate-600 dark:text-slate-300">
                            <p>
                                {$_('events.heard.strongest', { values: { score, time: formatTime(group.best_heard, { hour: '2-digit', minute: '2-digit', second: '2-digit' }) }, default: 'Strongest call {score}% at {time}' })}
                            </p>
                            {#if group.best_birdnet_id}
                                <audio class="w-full max-w-sm" controls preload="none" src={clip(group.best_birdnet_id)}>
                                    <track kind="captions" />
                                </audio>
                                {#if birdnetBase}
                                    <a
                                        href="{birdnetBase}/ui/detections/{group.best_birdnet_id}"
                                        target="_blank"
                                        rel="noopener noreferrer"
                                        class="btn btn-secondary inline-flex min-h-11 items-center px-3 text-xs"
                                    >{$_('audio.table.open_birdnet', { default: 'Open in BirdNET-Go' })}</a>
                                {/if}
                            {/if}
                        </div>
                    </div>
                {/if}
            </div>
        </li>
    {/each}
</ol>
