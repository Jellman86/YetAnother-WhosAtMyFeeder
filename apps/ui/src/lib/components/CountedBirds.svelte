<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { updateCountedBird, type BirdObservation, type SnapshotCandidate } from '../api';
    import { getErrorMessage } from '../utils/error-handling';
    import { toastStore } from '../stores/toast.svelte';

    interface Props {
        eventId: string;
        birds: BirdObservation[];
        candidates: SnapshotCandidate[];
        speciesOptions?: string[];
        onchanged: (bird: BirdObservation) => void;
    }

    let { eventId, birds, candidates, speciesOptions = [], onchanged }: Props = $props();
    let imageSize = $state({ width: 0, height: 0 });
    let editingId = $state<number | null>(null);
    let speciesInput = $state('');
    let savingId = $state<number | null>(null);
    const visibleBirds = $derived(birds.filter((bird) => !bird.is_hidden));
    const hintOnly = $derived(birds.length > 0 && birds.every((bird) => bird.detector_confidence === null));
    const speciesSuggestions = $derived(
        speciesInput.trim().length >= 2
            ? speciesOptions.filter((name) => name.toLowerCase().includes(speciesInput.trim().toLowerCase())).slice(0, 5)
            : []
    );
    const countedFrame = $derived(
        candidates.find((candidate) =>
            candidate.source_mode === 'full_frame'
            && birds.length > 0
            && candidate.clip_variant === birds[0].clip_variant
            && candidate.frame_index === birds[0].frame_index
            && (candidate.image_url || candidate.thumbnail_url)
        ) ?? null
    );

    $effect(() => {
        void countedFrame?.candidate_id;
        imageSize = { width: 0, height: 0 };
    });

    function measureImage(event: Event): void {
        const image = event.currentTarget as HTMLImageElement;
        imageSize = { width: image.naturalWidth, height: image.naturalHeight };
    }

    function boxStyle(box: number[]): string {
        if (box.length !== 4 || imageSize.width <= 0 || imageSize.height <= 0) return 'display:none';
        const [left, top, right, bottom] = box;
        const x = Math.max(0, Math.min(left, imageSize.width));
        const y = Math.max(0, Math.min(top, imageSize.height));
        const width = Math.max(0, Math.min(right, imageSize.width) - x);
        const height = Math.max(0, Math.min(bottom, imageSize.height) - y);
        return `left:${x / imageSize.width * 100}%;top:${y / imageSize.height * 100}%;width:${width / imageSize.width * 100}%;height:${height / imageSize.height * 100}%`;
    }

    async function saveSpecies(bird: BirdObservation): Promise<void> {
        const species = speciesInput.trim();
        if (!species || savingId !== null) return;
        savingId = bird.id;
        try {
            onchanged(await updateCountedBird(eventId, bird.id, { species }));
            editingId = null;
        } catch (error) {
            toastStore.error(getErrorMessage(error));
        } finally {
            savingId = null;
        }
    }

    async function toggleHidden(bird: BirdObservation): Promise<void> {
        if (savingId !== null) return;
        savingId = bird.id;
        try {
            onchanged(await updateCountedBird(eventId, bird.id, { is_hidden: !bird.is_hidden }));
        } catch (error) {
            toastStore.error(getErrorMessage(error));
        } finally {
            savingId = null;
        }
    }
</script>

{#if birds.length > 0}
    <section class="space-y-3 border-t border-slate-200 pt-5 dark:border-slate-700" data-counted-birds>
        <div class="flex items-baseline justify-between gap-2">
            <h4 class="text-xs font-semibold uppercase tracking-[0.12em] text-slate-500 dark:text-slate-400">
                {$_('detection.counted_birds.title', { default: 'Birds found in this capture' })}
            </h4>
            <span class="font-display text-lg font-bold tabular-nums text-slate-900 dark:text-white" aria-label={$_('detection.counted_birds.count', { values: { count: visibleBirds.length }, default: 'Birds counted: {count}' })}>{visibleBirds.length}</span>
        </div>
        <p class="text-xs leading-5 text-slate-500 dark:text-slate-400">
            {hintOnly
                ? $_('detection.counted_birds.hint_only', { default: 'Only Frigate’s tracked bird was located; other birds may be visible.' })
                : $_('detection.counted_birds.note', { default: 'One analyzed frame; the detector can miss birds or mark other objects.' })}
        </p>
        {#if countedFrame}
            <div class="relative overflow-hidden rounded-xl bg-slate-950" data-counted-birds-frame>
                <img
                    src={countedFrame.image_url ?? countedFrame.thumbnail_url ?? ''}
                    alt={$_('detection.counted_birds.frame_alt', { default: 'Whole capture with counted birds marked' })}
                    class="block h-auto w-full"
                    onload={measureImage}
                />
                {#each birds as bird (bird.id)}
                    {#if !bird.is_hidden}
                        <span class="pointer-events-none absolute rounded-sm border-2 border-sky-300 shadow-[0_0_0_1px_rgba(15,23,42,0.65)]" style={boxStyle(bird.crop_box)} aria-hidden="true" data-counted-bird-outline>
                            <span class="absolute -top-5 left-0 rounded bg-sky-300 px-1.5 py-0.5 text-[10px] font-bold leading-none text-slate-950">{bird.bird_index + 1}</span>
                        </span>
                    {/if}
                {/each}
            </div>
        {/if}
        <ol class="space-y-1.5" data-counted-bird-list>
            {#each birds as bird (bird.id)}
                <li class="rounded-xl border border-slate-200 px-3 py-2 text-xs dark:border-slate-700">
                    <div class="flex flex-wrap items-center gap-2">
                        <span class="font-semibold tabular-nums text-slate-500 dark:text-slate-400">{bird.bird_index + 1}.</span>
                        <span class="min-w-0 flex-1 font-semibold {bird.is_hidden ? 'text-slate-400 line-through' : 'text-slate-800 dark:text-slate-100'}">{bird.species}</span>
                        {#if !bird.manual_species && !bird.is_hidden}
                            <span class="text-[10px] text-slate-500 dark:text-slate-400">{$_('detection.counted_birds.suggested', { default: 'Suggested' })}</span>
                        {/if}
                        <button type="button" class="min-h-9 rounded-lg px-2 font-semibold text-brand-700 hover:bg-brand-50 focus-ring dark:text-brand-300 dark:hover:bg-brand-950/30" disabled={savingId !== null} onclick={() => { editingId = editingId === bird.id ? null : bird.id; speciesInput = bird.species === 'Unknown Bird' ? '' : bird.species; }}>
                            {$_('detection.counted_birds.correct', { default: 'Correct' })}
                        </button>
                        <button type="button" class="min-h-9 rounded-lg px-2 font-semibold text-slate-600 hover:bg-slate-100 focus-ring dark:text-slate-300 dark:hover:bg-slate-800" disabled={savingId !== null} onclick={() => { void toggleHidden(bird); }}>
                            {bird.is_hidden ? $_('detection.counted_birds.restore', { default: 'Restore' }) : $_('detection.counted_birds.exclude', { default: 'Exclude' })}
                        </button>
                    </div>
                    {#if editingId === bird.id}
                        <form class="mt-2 flex gap-2" onsubmit={(event) => { event.preventDefault(); void saveSpecies(bird); }}>
                            <label class="min-w-0 flex-1">
                                <span class="sr-only">{$_('detection.counted_birds.species_label', { default: 'Species for bird' })} {bird.bird_index + 1}</span>
                                <input class="input-base w-full" maxlength="120" bind:value={speciesInput} required />
                            </label>
                            <button type="submit" class="btn btn-primary min-h-11 px-3 text-xs" disabled={savingId !== null || !speciesInput.trim()}>{$_('common.save', { default: 'Save' })}</button>
                        </form>
                        {#if speciesSuggestions.length > 0}
                            <ul class="mt-1 max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" aria-label={$_('detection.counted_birds.suggestions', { default: 'Matching species' })}>
                                {#each speciesSuggestions as suggestion (suggestion)}
                                    <li><button type="button" class="min-h-9 w-full rounded-md px-2 text-left text-xs text-slate-700 hover:bg-brand-50 focus-ring dark:text-slate-200 dark:hover:bg-brand-950/30" onclick={() => { speciesInput = suggestion; }}>{suggestion}</button></li>
                                {/each}
                            </ul>
                        {/if}
                    {/if}
                </li>
            {/each}
        </ol>
    </section>
{/if}
