<script lang="ts">
    /**
     * One Garden capture as a tile in the Explorer's card grid, in a visit card's shape: the
     * photograph with its time and score, then the subject. The marker on the photograph says
     * Garden in words, and a capture that needs a person says why beneath its name.
     */
    import { get } from 'svelte/store';
    import { _ } from 'svelte-i18n';
    import GardenPhotoPreview from './GardenPhotoPreview.svelte';
    import GardenVisitCaptures from './GardenVisitCaptures.svelte';
    import type { GardenCaptureScope } from '../utils/garden-visit-viewer.svelte';
    import GardenExplorerMarker from './GardenExplorerMarker.svelte';
    import type { GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { gardenEntryText, gardenEntryView, gardenRowDetail, gardenVisitLabel, type GardenVisit } from '../utils/garden-explorer';
    import { formatDate, formatTime } from '../utils/datetime';
    import { relativeDayLabel } from '../utils/day-label';
    import { SCORE_FILL, scoreBand } from '../utils/score-tone';

    let { capture, visit, scope, onopen, oncapture, onplay }: {
        capture: GardenCapture;
        /** Plays the capture's Frigate clip, as a bird card's play control does. */
        onplay?: (capture: GardenCapture) => void;
        /** The stay or position stack this capture leads, opened together. */
        visit?: GardenVisit;
        scope?: GardenCaptureScope;
        oncapture?: (capture: GardenCapture, index: number) => void;
        onopen: (capture: GardenCapture) => void;
    } = $props();

    let failedUrl = $state<string | null>(null);
    let failedCropUrl = $state<string | null>(null);
    let loadedUrl = $state<string | null>(null);
    const view = $derived(gardenEntryView(capture));
    const text = $derived(gardenEntryText(capture, view, (key, fallback, values) => get(_)(key, { values, default: fallback })));
    const detail = $derived(gardenRowDetail(capture, view));
    const canPlay = $derived(Boolean(onplay && capture.clip_event));
    const cropPhoto = $derived(capture.crop_url ? withAuthParams(capture.crop_url) : null);
    const fullPhoto = $derived(capture.snapshot_url ? withAuthParams(capture.snapshot_url) : null);
    const photo = $derived(cropPhoto && cropPhoto !== failedCropUrl ? cropPhoto : fullPhoto);
    const usingSavedCrop = $derived(Boolean(cropPhoto && photo === cropPhoto));
    const score = $derived(view.score === null ? null : Math.round(view.score * 100));
    const day = $derived(relativeDayLabel(capture.observed_at, $_) || formatDate(capture.observed_at));
    const grouped = $derived(gardenVisitLabel(visit, (key, fallback, values) => get(_)(key, { values, default: fallback })));
    const scoreDot = $derived(SCORE_FILL[scoreBand(view.score)]);
</script>

<article
    class="group relative flex h-full flex-col overflow-hidden rounded-2xl border bg-white/90 shadow-sm transition-[border-color,box-shadow] duration-200 ease-out animate-entrance hover:border-brand-500/40 hover:shadow-md dark:bg-slate-800/75
           {view.review ? 'border-attention-500/60' : 'border-slate-200/80 dark:border-slate-700/60'}"
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
            <div class="h-full w-full transition-opacity duration-300 {loadedUrl === photo ? 'opacity-100' : 'opacity-0'}">
                <GardenPhotoPreview
                    {capture}
                    src={photo} cropped={usingSavedCrop}
                    alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: capture.camera } })}
                    onload={() => (loadedUrl = photo)}
                    onerror={() => { if (usingSavedCrop) failedCropUrl = photo; else failedUrl = photo; }}
                />
            </div>
            <div class="absolute inset-0 bg-gradient-to-t from-black/60 via-transparent to-black/20 opacity-60"></div>
        {:else}
            <p class="absolute inset-0 flex items-center justify-center p-4 text-center text-xs text-slate-600 dark:text-slate-400">
                {capture.status === 'confirmed'
                    ? $_('garden.explorer.photo_expired_short', { default: 'Photo expired' })
                    : $_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}
            </p>
        {/if}
        <div class="absolute left-3 top-3 flex flex-wrap items-center gap-1.5">
            <GardenExplorerMarker overlay />
            {#if grouped}
                <!-- Several photos open from this one card, as a bird visit's captures do. -->
                <span class="inline-flex items-center rounded-full border border-white/10 bg-black/60 px-2 py-0.5 text-2xs font-bold text-white backdrop-blur-md" data-garden-card-group>
                    {grouped}
                </span>
            {/if}
        </div>
        <div class="absolute bottom-3 left-3 flex flex-nowrap items-center gap-2">
            <time class="flex min-h-11 items-center gap-1.5 rounded-full border border-white/10 bg-black/60 px-3 py-2 text-xs font-bold text-white backdrop-blur-md" datetime={capture.observed_at}>
                <svg class="h-3 w-3 text-brand-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                {formatTime(capture.observed_at)}
            </time>
            {#if score !== null}
                <span class="flex min-h-11 items-center gap-1.5 rounded-full border border-white/10 bg-black/60 px-3 py-2 text-xs font-bold text-white backdrop-blur-md">
                    <span class="h-2 w-2 rounded-full {scoreDot}" aria-hidden="true"></span>
                    {score}%<span class="sr-only">{$_('garden.explorer.score_hint', { values: { score }, default: 'Species model score {score}%' })}</span>
                </span>
            {/if}
            {#if canPlay}
                <!-- Above the card's open control, so it plays the clip rather than opening the record. -->
                <button
                    type="button"
                    onclick={(event) => { event.stopPropagation(); onplay?.(capture); }}
                    aria-label={$_('detection.play_video', { values: { species: text.title } })}
                    class="relative z-20 inline-flex h-11 w-11 items-center justify-center rounded-full border border-white/25 bg-black/55 text-white shadow-lg backdrop-blur-sm transition-colors duration-200 hover:bg-brand-700/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                    data-garden-card-play
                >
                    <svg class="h-3.5 w-3.5" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><path d="M8 5v14l11-7z" /></svg>
                </button>
            {/if}
        </div>
    </div>
    <div class="flex flex-1 flex-col gap-2 p-4">
        <div>
            <h3 class="truncate text-lg font-bold leading-tight tracking-tight text-slate-900 dark:text-white" title={text.title}>{text.title}</h3>
            {#if detail.showState}
                <p class="mt-1 flex items-start gap-1.5 text-2xs font-semibold {view.review ? 'text-attention-800 dark:text-attention-300' : 'text-slate-600 dark:text-slate-400'}">
                    {#if view.review}<span class="mt-1 h-2 w-2 shrink-0 rounded-full bg-attention-500" aria-hidden="true"></span>{/if}
                    {text.state}
                </p>
            {:else}
                <p class="mt-1 truncate text-2xs font-semibold italic text-slate-600 dark:text-slate-400" data-garden-card-scientific>{detail.scientific}</p>
            {/if}
        </div>
        <div class="mt-auto flex items-center gap-1.5 truncate text-2xs font-medium text-slate-500 dark:text-slate-400">
            <span>{day}</span>
            <span class="text-slate-300 dark:text-slate-600">&middot;</span>
            <span class="truncate">{capture.camera}</span>
        </div>
    </div>
    {#if visit && scope && oncapture}
        <div class="relative z-20"><GardenVisitCaptures {visit} {scope} floating onselect={oncapture} /></div>
    {/if}
</article>
