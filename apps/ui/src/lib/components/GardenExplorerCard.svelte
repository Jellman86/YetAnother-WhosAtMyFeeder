<script lang="ts">
    /**
     * One Garden capture as a tile in the Explorer's card grid, in a visit card's shape: the
     * photograph with its time and score, then the subject. The marker on the photograph says
     * Garden in words, and a capture that needs a person says why beneath its name.
     */
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import type { GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { gardenEntryText, gardenEntryView } from '../utils/garden-explorer';
    import { formatDate, formatTime } from '../utils/datetime';
    import { relativeDayLabel } from '../utils/day-label';

    let { capture, onopen }: { capture: GardenCapture; onopen: (capture: GardenCapture) => void } = $props();

    let failedUrl = $state<string | null>(null);
    let loadedUrl = $state<string | null>(null);
    const view = $derived(gardenEntryView(capture));
    const text = $derived(gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback })));
    const photo = $derived(capture.snapshot_url ? withAuthParams(capture.snapshot_url) : null);
    const score = $derived(view.score === null ? null : Math.round(view.score * 100));
    const day = $derived(relativeDayLabel(capture.observed_at, $_) || formatDate(capture.observed_at));
</script>

<article
    class="group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-white/90 shadow-sm transition-[border-color,box-shadow] duration-200 hover:border-brand-500/40 hover:shadow-md dark:bg-slate-800/75
           {view.review ? 'border-amber-500/60' : 'border-slate-200/80 dark:border-slate-700/60'}"
    data-garden-card={capture.status}
>
    <button
        type="button"
        class="absolute inset-0 z-10 rounded-2xl focus:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
        aria-label={$_('garden.explorer.open', { values: { subject: `${text.title}, ${formatTime(capture.observed_at)}` }, default: 'Open Garden capture: {subject}' })}
        onclick={() => onopen(capture)}
    ></button>
    <div class="relative aspect-[4/3] overflow-hidden bg-slate-100 dark:bg-slate-800">
        {#if photo && failedUrl !== photo}
            <img
                src={photo}
                alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: capture.camera } })}
                loading="lazy"
                class="h-full w-full object-cover transition-opacity duration-300 motion-reduce:transition-none {loadedUrl === photo ? 'opacity-100' : 'opacity-0'}"
                onload={() => (loadedUrl = photo)}
                onerror={() => (failedUrl = photo)}
            />
            <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20 opacity-60"></div>
        {:else}
            <p class="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-slate-600 dark:text-slate-400">
                {capture.status === 'confirmed'
                    ? $_('garden.explorer.photo_expired_short', { default: 'Photo expired' })
                    : $_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}
            </p>
        {/if}
        <div class="absolute left-3 top-3"><GardenExplorerMarker overlay /></div>
        <div class="absolute bottom-3 left-3 flex flex-nowrap items-center gap-2">
            <time class="flex min-h-11 items-center rounded-full border border-white/10 bg-black/60 px-3 py-2 text-xs font-bold text-white backdrop-blur-md" datetime={capture.observed_at}>
                {formatTime(capture.observed_at)}
            </time>
            {#if score !== null}
                <span class="flex min-h-11 items-center rounded-full border border-white/10 bg-black/60 px-3 py-2 text-xs font-bold text-white backdrop-blur-md">
                    {score}%<span class="sr-only">{$_('garden.explorer.score_hint', { values: { score }, default: 'Species model score {score}%' })}</span>
                </span>
            {/if}
        </div>
    </div>
    <div class="flex flex-1 flex-col gap-2 p-4">
        <div>
            <h3 class="truncate text-lg font-bold leading-tight tracking-tight text-slate-900 dark:text-white" title={text.title}>{text.title}</h3>
            <p class="mt-1 flex items-start gap-1.5 text-2xs font-semibold {view.review ? 'text-amber-800 dark:text-amber-300' : 'text-slate-600 dark:text-slate-400'}">
                {#if view.review}<span class="mt-1 h-2 w-2 shrink-0 rounded-full bg-amber-500" aria-hidden="true"></span>{/if}
                {text.state}
            </p>
        </div>
        <div class="mt-auto flex items-center gap-1.5 truncate text-2xs font-medium text-slate-500 dark:text-slate-400">
            <span>{day}</span>
            <span class="text-slate-300 dark:text-slate-600">&middot;</span>
            <span class="truncate">{capture.camera}</span>
        </div>
    </div>
</article>
