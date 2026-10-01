<script lang="ts">
    import { onDestroy, tick } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { updateCountedBird, type BirdObservation, type SnapshotCandidate } from '../api';
    import { getErrorMessage } from '../utils/error-handling';
    import { toastStore } from '../stores/toast.svelte';
    import {
        birdReadingOrder,
        captureBirdCounts,
        cropBackground,
        isUnknownBird,
        repeatedSpeciesPositions,
        resolveCountScene,
        sceneBoxPercent,
        sceneGeometryIsValid,
        type SourceSize
    } from '../utils/count-scene';

    interface Props {
        eventId: string;
        birds: BirdObservation[];
        candidates: SnapshotCandidate[];
        /** The photograph's own candidate, so the scene can say whether it is the same moment. */
        photograph?: SnapshotCandidate | null;
        speciesOptions?: string[];
        /** Advanced by the caller whenever the birds are reread for this capture. */
        generation?: number;
        loading?: boolean;
        error?: boolean;
        regenerating?: boolean;
        /** Counting is switched on, so "not counted" is worth saying. */
        countingAvailable?: boolean;
        onretry?: () => void;
        onchanged: (bird: BirdObservation) => void;
        /** An edit landed after the birds were reread; the caller reads them again. */
        onstale?: () => void;
    }

    let {
        eventId,
        birds,
        candidates,
        photograph = null,
        speciesOptions = [],
        generation = 0,
        loading = false,
        error = false,
        regenerating = false,
        countingAvailable = false,
        onretry,
        onchanged,
        onstale
    }: Props = $props();

    /** Rows shown before the list asks to be expanded; the total is always stated. */
    const COLLAPSED_ROWS = 6;
    const CROP_EDGE = 44;

    let selectedId = $state<number | null>(null);
    let previewId = $state<number | null>(null);
    let editingId = $state<number | null>(null);
    let expanded = $state(false);
    let speciesInput = $state('');
    let saving = $state<{ birdId: number; token: number } | null>(null);
    let saveToken = 0;
    let destroyed = false;
    let sectionEl = $state<HTMLElement | null>(null);
    onDestroy(() => {
        destroyed = true;
    });

    /** The decoded size, remembered with the image it belongs to so a late load cannot misplace boxes. */
    let measured = $state<{ src: string; size: SourceSize | null } | null>(null);

    const scene = $derived(resolveCountScene(birds, candidates));
    const sceneSrc = $derived(scene.status === 'ready' ? scene.imageUrl : null);
    const sceneSize = $derived(measured && measured.src === sceneSrc ? measured.size : null);
    const sceneFailed = $derived(!!measured && measured.src === sceneSrc && measured.size === null);
    const outlined = $derived(!!sceneSize && sceneGeometryIsValid(birds, sceneSize));
    const unavailable = $derived.by((): string | null => {
        if (scene.status === 'unavailable') return scene.reason;
        if (sceneFailed) return 'load_failed';
        if (sceneSize && !outlined) return 'geometry';
        return null;
    });

    const counts = $derived(captureBirdCounts(birds));
    const hintOnly = $derived(birds.length > 0 && birds.every((bird) => bird.detector_confidence === null));
    const ordered = $derived(birdReadingOrder(birds));
    const rows = $derived([...ordered.filter((bird) => !bird.is_hidden), ...ordered.filter((bird) => bird.is_hidden)]);
    const shownRows = $derived(expanded ? rows : rows.slice(0, COLLAPSED_ROWS));
    const firstExcludedId = $derived(rows.find((bird) => bird.is_hidden)?.id ?? null);
    const positions = $derived(repeatedSpeciesPositions(birds));
    const highlightedId = $derived(previewId ?? selectedId);
    const busy = $derived(saving !== null || regenerating);
    const speciesSuggestions = $derived(
        speciesInput.trim().length >= 2
            ? speciesOptions.filter((name) => name.toLowerCase().includes(speciesInput.trim().toLowerCase())).slice(0, 5)
            : []
    );
    const samePhotoFrame = $derived(
        scene.status === 'ready' && photograph
            ? photograph.clip_variant === scene.clipVariant && photograph.frame_index === scene.frameIndex
            : null
    );

    $effect(() => {
        // A reread can drop a bird; its selection and editor go with it.
        const ids = new Set(birds.map((bird) => bird.id));
        if (selectedId !== null && !ids.has(selectedId)) selectedId = null;
        if (editingId !== null && !ids.has(editingId)) editingId = null;
        if (previewId !== null && !ids.has(previewId)) previewId = null;
    });

    function measure(event: Event): void {
        const image = event.currentTarget as HTMLImageElement;
        const src = image.getAttribute('src');
        if (!src || src !== sceneSrc) return;
        measured = { src, size: { width: image.naturalWidth, height: image.naturalHeight } };
    }

    function measureFailed(event: Event): void {
        const src = (event.currentTarget as HTMLImageElement).getAttribute('src');
        if (src && src === sceneSrc) measured = { src, size: null };
    }

    function speciesName(bird: BirdObservation): string {
        return isUnknownBird(bird)
            ? $_('detection.counted_birds.unknown_bird', { default: 'Unknown bird' })
            : bird.species;
    }

    function positionText(bird: BirdObservation): string | null {
        const position = positions.get(bird.id);
        return position
            ? $_('detection.counted_birds.position', {
                  values: { ordinal: position.ordinal, total: position.total },
                  default: '{ordinal} of {total} from the left'
              })
            : null;
    }

    function birdLabel(bird: BirdObservation): string {
        const position = positionText(bird);
        return position ? `${speciesName(bird)}, ${position}` : speciesName(bird);
    }

    function percent(score: number | null | undefined): string {
        return `${Math.round((score ?? 0) * 100)}%`;
    }

    /** Pixels, not rem: the cut is computed for this exact edge, whatever the text size. */
    function cropStyle(bird: BirdObservation): string {
        const box = `width:${CROP_EDGE}px;height:${CROP_EDGE}px`;
        if (!outlined || !sceneSize || !sceneSrc) return box;
        const crop = cropBackground(bird.crop_box, sceneSize, CROP_EDGE);
        return `${box};background-image:url(${JSON.stringify(sceneSrc)});background-size:${crop.width}px ${crop.height}px;background-position:${crop.offsetX}px ${crop.offsetY}px`;
    }

    function boxStyle(bird: BirdObservation): string {
        if (!sceneSize) return 'display:none';
        const box = sceneBoxPercent(bird.crop_box, sceneSize, 16 / 9);
        return `left:${box.left}%;top:${box.top}%;width:${box.width}%;height:${box.height}%`;
    }

    function toggle(bird: BirdObservation): void {
        // Content scrolling under a resting pointer must not outrank what was just chosen.
        previewId = bird.id;
        if (selectedId === bird.id) {
            selectedId = null;
            if (editingId === bird.id) editingId = null;
            return;
        }
        selectedId = bird.id;
        if (editingId !== bird.id) editingId = null;
    }

    function startEditing(bird: BirdObservation): void {
        editingId = editingId === bird.id ? null : bird.id;
        speciesInput = isUnknownBird(bird) ? '' : bird.species;
    }

    function collapse(): void {
        expanded = false;
        const shown = new Set(rows.slice(0, COLLAPSED_ROWS).map((bird) => bird.id));
        if (selectedId !== null && !shown.has(selectedId)) selectedId = null;
    }

    /**
     * Excluding or restoring moves the row between groups, and a moved element drops focus to
     * the page, where Escape no longer reaches the dialog. Focus returns to the same action.
     */
    async function keepFocusOn(birdId: number, control: 'correct' | 'visibility'): Promise<void> {
        await tick();
        // Only when focus was lost; someone who has moved on keeps their place.
        if (document.activeElement && document.activeElement !== document.body) return;
        const row = sectionEl?.querySelector(`[data-counted-bird-row="${birdId}"]`);
        (row?.querySelector<HTMLElement>(`[data-counted-bird-${control}]`) ??
            row?.querySelector<HTMLElement>('[data-counted-bird-select]'))?.focus();
    }

    /** One edit at a time; its answer only applies to the capture and reading it was made against. */
    async function save(bird: BirdObservation, change: { species: string } | { is_hidden: boolean }): Promise<void> {
        if (saving !== null || regenerating) return;
        const token = ++saveToken;
        const requestEvent = eventId;
        const requestGeneration = generation;
        saving = { birdId: bird.id, token };
        try {
            const updated = await updateCountedBird(requestEvent, bird.id, change);
            if (destroyed || requestEvent !== eventId) return;
            if (requestGeneration !== generation || updated.id !== bird.id) {
                onstale?.();
                return;
            }
            onchanged(updated);
            if ('species' in change && editingId === bird.id) editingId = null;
        } catch (failure) {
            if (!destroyed && requestEvent === eventId) toastStore.error(getErrorMessage(failure));
        } finally {
            if (saving?.token === token) saving = null;
        }
        // The disabled button lost focus while saving; it can take it back once enabled again.
        if (!destroyed && requestEvent === eventId) await keepFocusOn(bird.id, 'species' in change ? 'correct' : 'visibility');
    }
</script>

<!-- Nothing while the first read is pending: most captures have no counted birds, and a passing
     loading line would shift the record for nothing. -->
{#if error || regenerating || birds.length > 0 || (countingAvailable && !loading)}
    <section bind:this={sectionEl} class="space-y-3 break-words border-t border-slate-200 pt-5 dark:border-slate-700" data-counted-birds aria-labelledby="counted-birds-title-{eventId}">
        <div class="flex items-baseline justify-between gap-3">
            <h4 id="counted-birds-title-{eventId}" class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                {$_('detection.counted_birds.title', { default: 'Birds found in this capture' })}
            </h4>
            {#if birds.length > 0}
                <span
                    class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white"
                    aria-label={$_('detection.counted_birds.count', { values: { count: counts.counted }, default: 'Birds counted: {count}' })}
                    data-counted-birds-total
                >{counts.counted}</span>
            {/if}
        </div>

        {#if regenerating}
            <p class="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-300" role="status" data-counted-birds-state="recounting">
                <span class="inline-block h-3 w-3 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin" aria-hidden="true"></span>
                {$_('detection.counted_birds.recounting', { default: 'Recounting the birds in this capture' })}
            </p>
        {/if}

        {#if error}
            <div class="flex flex-wrap items-center gap-2 text-xs text-slate-600 dark:text-slate-300" role="alert" data-counted-birds-state="error">
                <span>{$_('detection.counted_birds.error', { default: 'The birds in this capture could not be loaded.' })}</span>
                {#if onretry}
                    <button type="button" class="btn btn-ghost min-h-11 min-w-11 px-3 text-xs focus-ring" onclick={onretry}>
                        {$_('common.retry', { default: 'Retry' })}
                    </button>
                {/if}
            </div>
        {:else if birds.length === 0 && !regenerating}
            <p class="text-xs leading-5 text-slate-500 dark:text-slate-400" data-counted-birds-state="not-counted">
                {$_('detection.counted_birds.not_counted', { default: 'No birds are counted for this capture. That is not the same as none being there.' })}
            </p>
        {/if}

        {#if birds.length > 0}
            <p class="flex flex-wrap gap-x-3 gap-y-1 text-xs text-slate-600 dark:text-slate-300" data-counted-birds-summary>
                <span>{$_('detection.counted_birds.summary_species', { values: { count: counts.species }, default: 'Species: {count}' })}</span>
                <span>{$_('detection.counted_birds.summary_unknown', { values: { count: counts.unknown }, default: 'Unknown: {count}' })}</span>
                {#if counts.excluded > 0}
                    <span>{$_('detection.counted_birds.summary_excluded', { values: { count: counts.excluded }, default: 'Excluded: {count}' })}</span>
                {/if}
            </p>
            <p class="text-xs leading-5 text-slate-500 dark:text-slate-400">
                {hintOnly
                    ? $_('detection.counted_birds.hint_only', { default: 'Only Frigate’s tracked bird was located; other birds may be visible.' })
                    : $_('detection.counted_birds.note', { default: 'Counted on one analysed frame. The detector can miss birds or mark other objects, and a bird here is not followed across frames.' })}
            </p>

            {#if scene.status === 'ready'}
                <!-- The counted frame keeps its box whatever happens to its image: a frame that fails
                     to load becomes a placeholder of the same size, and one whose pixels cannot carry
                     the boxes is still shown, without outlines. -->
                <figure class="space-y-1.5" data-counted-birds-scene>
                    <!-- Reserve the same box before decoding. Outlines map to the contained
                         image's pixels, excluding any letterbox, without moving the bird rows. -->
                    <div
                        class="relative aspect-video w-full overflow-hidden rounded-xl bg-slate-950"
                        data-counted-birds-frame
                    >
                        {#if sceneFailed}
                            <span class="absolute inset-0 flex items-center justify-center text-slate-700" aria-hidden="true" data-media-placeholder>
                                <svg class="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                </svg>
                            </span>
                        {:else}
                            <img
                                src={scene.imageUrl}
                                alt={$_('detection.counted_birds.frame_alt', { default: 'Whole capture with counted birds marked' })}
                                class="absolute inset-0 block h-full w-full object-contain"
                                decoding="async"
                                onload={measure}
                                onerror={measureFailed}
                            />
                        {/if}
                        {#if outlined}
                            {#each rows as bird (bird.id)}
                                {#if !bird.is_hidden || bird.id === highlightedId}
                                    {@const lit = bird.id === highlightedId}
                                    <span
                                        class="pointer-events-none absolute rounded-sm motion-safe:transition-[border-color,box-shadow] motion-safe:duration-150 {lit
                                            ? bird.is_hidden
                                                ? 'z-20 border-2 border-dashed border-slate-200 shadow-[0_0_0_9999px_rgba(2,6,23,0.45)]'
                                                : 'z-20 border-2 border-sky-300 shadow-[0_0_0_9999px_rgba(2,6,23,0.45)]'
                                            : 'z-10 border border-white/80 shadow-[0_0_0_1px_rgba(15,23,42,0.6)]'}"
                                        style={boxStyle(bird)}
                                        aria-hidden="true"
                                        data-counted-bird-outline={bird.id}
                                        data-lit={lit ? 'true' : 'false'}
                                    >
                                        {#if lit}
                                            <span class="absolute bottom-full left-0 mb-1 max-w-48 truncate rounded bg-sky-300 px-1.5 py-0.5 text-xs font-bold leading-tight text-slate-950" data-counted-bird-tag>
                                                {bird.is_hidden ? $_('detection.counted_birds.excluded_tag', { values: { bird: birdLabel(bird) }, default: '{bird}, excluded' }) : birdLabel(bird)}
                                            </span>
                                        {/if}
                                    </span>
                                {/if}
                            {/each}
                        {/if}
                    </div>
                    <figcaption class="text-xs leading-5 text-slate-500 dark:text-slate-400" data-counted-birds-provenance>
                        {$_('detection.counted_birds.scene_caption', {
                            values: {
                                frame: scene.frameIndex,
                                clip: $_(`detection.counted_birds.clip_${['event', 'recording', 'frigate_snapshot'].includes(scene.clipVariant) ? scene.clipVariant : 'other'}`, { default: 'a retained clip' })
                            },
                            default: 'Counted on frame {frame} of {clip}.'
                        })}
                        {#if unavailable}
                            <span class="text-slate-600 dark:text-slate-300" data-counted-birds-unavailable={unavailable}>
                                {$_(`detection.counted_birds.unavailable_${unavailable}`, { default: 'The birds cannot be outlined on the counted frame.' })}
                            </span>
                        {:else if samePhotoFrame === true}
                            {$_('detection.counted_birds.scene_same_frame', { default: 'The photograph comes from this frame.' })}
                        {:else if samePhotoFrame === false}
                            {$_('detection.counted_birds.scene_other_frame', { default: 'The photograph comes from a different frame, so birds may sit differently there.' })}
                        {/if}
                    </figcaption>
                </figure>
            {:else if unavailable && unavailable !== 'no_birds'}
                <p class="text-xs leading-5 text-slate-600 dark:text-slate-300" data-counted-birds-unavailable={unavailable}>
                    {$_(`detection.counted_birds.unavailable_${unavailable}`, { default: 'The birds cannot be outlined on the counted frame.' })}
                </p>
            {/if}

            <ul class="divide-y divide-slate-200/70 border-y border-slate-200/70 dark:divide-slate-700/50 dark:border-slate-700/50" data-counted-bird-list>
                {#each shownRows as bird (bird.id)}
                    {@const open = selectedId === bird.id}
                    {@const unknown = isUnknownBird(bird)}
                    {@const position = positionText(bird)}
                    {#if bird.id === firstExcludedId}
                        <li class="pb-1 pt-3 text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400" data-counted-birds-excluded-heading>
                            {$_('detection.counted_birds.excluded_heading', { default: 'Excluded, not counted' })}
                        </li>
                    {/if}
                    <li data-counted-bird-row={bird.id} data-excluded={bird.is_hidden ? 'true' : 'false'}>
                        <button
                            type="button"
                            class="flex min-h-11 w-full items-center gap-2 rounded-lg px-1 py-1.5 text-left transition-colors hover:bg-slate-50 focus-ring dark:hover:bg-slate-800/60 {open ? 'bg-slate-50 dark:bg-slate-800/60' : ''}"
                            aria-expanded={open}
                            aria-controls="counted-bird-{bird.id}"
                            onclick={() => toggle(bird)}
                            onpointermove={(event) => { if (event.pointerType !== 'touch' && previewId !== bird.id) previewId = bird.id; }}
                            onpointerleave={() => { if (previewId === bird.id) previewId = null; }}
                            onfocus={() => { previewId = bird.id; }}
                            onblur={() => { if (previewId === bird.id) previewId = null; }}
                            data-counted-bird-select
                        >
                            <span
                                class="relative shrink-0 overflow-hidden rounded-md bg-slate-200 bg-no-repeat dark:bg-slate-700 {bird.id === highlightedId ? 'ring-2 ring-sky-400' : ''} {bird.is_hidden ? 'opacity-50 grayscale' : ''}"
                                style={cropStyle(bird)}
                                aria-hidden="true"
                                data-counted-bird-crop={outlined ? 'scene' : 'placeholder'}
                            >
                                {#if !outlined}
                                    <svg class="absolute inset-0 m-auto h-5 w-5 text-slate-400 dark:text-slate-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path stroke-linecap="round" stroke-linejoin="round" d="M16 7h.01M3.4 18H12a8 8 0 0 0 8-8V7a4 4 0 0 0-7.28-2.3L2 20" /><path stroke-linecap="round" stroke-linejoin="round" d="m20 7 2 .5-2 .5M10 18v3M14 17.75V21" /></svg>
                                {/if}
                            </span>
                            <span class="min-w-0 flex-1">
                                <span class="block break-words text-sm font-semibold {bird.is_hidden ? 'text-slate-500 dark:text-slate-400' : 'text-slate-900 dark:text-white'}">{speciesName(bird)}</span>
                                <span class="flex flex-wrap gap-x-1 text-xs text-slate-500 dark:text-slate-400">
                                    {#if position}<span>{position}</span>{/if}
                                    {#if bird.manual_species}
                                        <span>{$_('detection.counted_birds.corrected', { default: 'Your correction' })}</span>
                                    {:else if unknown && bird.classifier_label}
                                        <span>{$_('detection.counted_birds.too_low_to_name', { default: 'Too uncertain to name' })}</span>
                                    {/if}
                                    {#if !bird.manual_species}
                                        <!-- On a phone the score joins this line, leaving the name the width it needs. -->
                                        <span class="font-bold tabular-nums text-slate-600 sm:hidden dark:text-slate-300" aria-hidden="true">{percent(bird.classifier_score)}</span>
                                    {/if}
                                </span>
                            </span>
                            {#if !bird.manual_species}
                                <span class="shrink-0 text-xs font-bold tabular-nums text-slate-600 dark:text-slate-300">
                                    <span class="sr-only">{$_('detection.counted_birds.score_label', { default: 'This bird’s own species score' })}</span>
                                    <span class="hidden sm:inline">{percent(bird.classifier_score)}</span>
                                    <span class="sr-only sm:hidden">{percent(bird.classifier_score)}</span>
                                </span>
                            {/if}
                            <svg class="h-4 w-4 shrink-0 text-slate-400 transition-transform motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 8 5 5 5-5" /></svg>
                        </button>

                        {#if open}
                            <div id="counted-bird-{bird.id}" class="space-y-2 pb-3 pl-2 pr-1 pt-1 text-xs sm:pl-14 text-slate-600 dark:text-slate-300" data-counted-bird-details>
                                <p>
                                    {#if unknown && bird.classifier_label && !bird.manual_species}
                                        {$_('detection.counted_birds.best_guess', { values: { label: bird.classifier_label, score: percent(bird.classifier_score) }, default: 'Best guess {label} at {score}, too low to name.' })}
                                    {:else if bird.manual_species && bird.classifier_label && bird.classifier_label !== bird.species}
                                        {$_('detection.counted_birds.model_suggested', { values: { label: bird.classifier_label, score: percent(bird.classifier_score) }, default: 'The model suggested {label} at {score}.' })}
                                    {:else if !bird.manual_species}
                                        {$_('detection.counted_birds.own_score', { values: { score: percent(bird.classifier_score) }, default: 'This bird scored {score} on its own, separately from the photograph.' })}
                                    {/if}
                                    {bird.detector_confidence === null
                                        ? $_('detection.counted_birds.located_hint', { default: 'Located from Frigate’s tracked box.' })
                                        : $_('detection.counted_birds.located', { values: { score: percent(bird.detector_confidence) }, default: 'Located with {score} detector confidence.' })}
                                </p>
                                <div class="flex flex-wrap gap-2">
                                    {#if !bird.is_hidden}
                                        <button
                                            type="button"
                                            class="btn btn-secondary min-h-11 min-w-11 px-3 text-xs focus-ring"
                                            aria-expanded={editingId === bird.id}
                                            disabled={busy}
                                            onclick={() => startEditing(bird)}
                                            data-counted-bird-correct
                                        >
                                            {$_('detection.counted_birds.correct_species', { default: 'Change species' })}
                                        </button>
                                    {/if}
                                    <button
                                        type="button"
                                        class="btn btn-ghost min-h-11 min-w-11 px-3 text-xs focus-ring"
                                        disabled={busy}
                                        onclick={() => { void save(bird, { is_hidden: !bird.is_hidden }); }}
                                        data-counted-bird-visibility
                                    >
                                        {#if saving?.birdId === bird.id}
                                            <span class="inline-block h-3 w-3 rounded-full border-2 border-current border-t-transparent motion-safe:animate-spin" aria-hidden="true"></span>
                                        {/if}
                                        {bird.is_hidden
                                            ? $_('detection.counted_birds.restore_to_count', { default: 'Count this bird again' })
                                            : $_('detection.counted_birds.exclude_from_count', { default: 'Exclude from the count' })}
                                    </button>
                                </div>
                                {#if editingId === bird.id}
                                    <form class="flex flex-wrap gap-2" onsubmit={(event) => { event.preventDefault(); const species = speciesInput.trim(); if (species) void save(bird, { species }); }}>
                                        <label class="min-w-0 flex-1 basis-32">
                                            <span class="sr-only">{$_('detection.counted_birds.species_for', { values: { bird: birdLabel(bird) }, default: 'Species for {bird}' })}</span>
                                            <input class="input-base min-h-11 w-full" maxlength="120" bind:value={speciesInput} required />
                                        </label>
                                        <button type="submit" class="btn btn-primary min-h-11 px-3 text-xs" disabled={busy || !speciesInput.trim()}>
                                            {$_('detection.counted_birds.save_species', { default: 'Save species' })}
                                        </button>
                                    </form>
                                    {#if speciesSuggestions.length > 0}
                                        <ul class="max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" aria-label={$_('detection.counted_birds.suggestions', { default: 'Matching species' })}>
                                            {#each speciesSuggestions as suggestion (suggestion)}
                                                <li><button type="button" class="btn btn-ghost min-h-11 min-w-11 w-full justify-start rounded-md px-2 text-left text-xs text-slate-700 hover:bg-brand-50 focus-ring dark:text-slate-200 dark:hover:bg-brand-950/30" onclick={() => { speciesInput = suggestion; }}>{suggestion}</button></li>
                                            {/each}
                                        </ul>
                                    {/if}
                                {/if}
                            </div>
                        {/if}
                    </li>
                {/each}
            </ul>
            {#if rows.length > COLLAPSED_ROWS}
                <button
                    type="button"
                    class="btn btn-ghost min-h-11 w-full justify-center text-xs focus-ring"
                    aria-expanded={expanded}
                    onclick={() => { if (expanded) collapse(); else expanded = true; }}
                    data-counted-birds-expand
                >
                    {expanded
                        ? $_('detection.counted_birds.show_fewer', { default: 'Show fewer birds' })
                        : $_('detection.counted_birds.show_all', { values: { count: rows.length }, default: 'Show all {count} birds' })}
                </button>
            {/if}
        {/if}
    </section>
{/if}
