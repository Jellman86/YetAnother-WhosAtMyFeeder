<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { searchSpecies, type SearchResult } from '../api';
    import { getManualTagSearchOptions } from '../search/manual-tag-search';
    import { speciesPickerNames } from '../utils/species-picker';

    let { birdLabel, busy, onsave }: { birdLabel: string; busy: boolean; onsave: (species: string) => void } = $props();
    let input = $state('');
    let choice = $state<{ id: string; input: string } | null>(null);
    let answer = $state.raw<{ term: string; results: SearchResult[]; failed: boolean } | null>(null);
    const term = $derived(input.trim());
    const selected = $derived(choice?.input === input ? choice : null);
    const current = $derived(answer?.term === term ? answer : null);
    const matches = $derived((current?.results ?? []).map(result => ({ id: result.id, ...speciesPickerNames(result) })));

    $effect(() => {
        const query = term;
        if (selected) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            const options = getManualTagSearchOptions(query);
            try {
                const results = await searchSpecies(query, options.limit, options.hydrateMissing || !query, controller.signal);
                if (!controller.signal.aborted) answer = { term: query, results, failed: false };
            } catch {
                if (!controller.signal.aborted) answer = { term: query, results: [], failed: true };
            }
        }, 200);
        return () => { clearTimeout(timer); controller.abort(); };
    });
</script>

<form class="flex flex-wrap gap-2" onsubmit={(event) => { event.preventDefault(); if (selected && !busy) onsave(selected.id); }}>
    <label class="min-w-0 flex-1 basis-32">
        <span class="sr-only">{$_('detection.counted_birds.species_for', { values: { bird: birdLabel }, default: 'Species for {bird}' })}</span>
        <input class="input-base min-h-11 w-full" maxlength="120" bind:value={input} oninput={() => { choice = null; }} disabled={busy} autocomplete="off" />
    </label>
    <button type="submit" class="btn btn-primary min-h-11 px-3 text-xs" disabled={busy || !selected}>
        {$_('detection.counted_birds.save_species', { default: 'Save species' })}
    </button>
</form>
{#if !selected}
    <p class="text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
        {#if !current}
            {$_('common.loading', { default: 'Loading…' })}
        {:else if current.failed}
            {$_('dashboard.review_session.search_failed', { default: 'Couldn’t search species. Edit the search to try again.' })}
        {:else if matches.length === 0}
            {$_('dashboard.review_session.no_matches', { default: 'No species matches that. Try fewer letters.' })}
        {:else}
            {$_('detection.counted_birds.choose_species', { default: 'Search by common or scientific name, then choose a species.' })}
        {/if}
    </p>
    {#if matches.length > 0}
        <ul class="max-h-40 overflow-y-auto rounded-lg border border-slate-200 bg-white p-1 dark:border-slate-700 dark:bg-slate-900" aria-label={$_('detection.counted_birds.suggestions', { default: 'Matching species' })}>
            {#each matches as match (match.id)}
                <li><button type="button" class="btn btn-ghost min-h-11 min-w-11 w-full flex-col items-start justify-center rounded-md px-2 text-left text-xs focus-ring" disabled={busy} onclick={() => { input = match.primary; choice = { id: match.id, input: match.primary }; }}>
                    <span class="break-words">{match.primary}</span>
                    {#if match.secondary}<span class="break-words font-normal italic text-slate-500 dark:text-slate-400">{match.secondary}</span>{/if}
                </button></li>
            {/each}
        </ul>
    {/if}
{/if}
