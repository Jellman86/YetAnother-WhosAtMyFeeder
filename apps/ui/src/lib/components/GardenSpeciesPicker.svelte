<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { searchGardenSpecies, type GardenSpecies } from '../api/garden';

    let { busy, onsave, oncancel }: { busy: boolean; onsave: (id: number) => void; oncancel: () => void } = $props();
    let input = $state('');
    let choice = $state<GardenSpecies | null>(null);
    let answer = $state.raw<{ term: string; values: GardenSpecies[]; failed: boolean } | null>(null);
    const term = $derived(input.trim());
    const current = $derived(answer?.term === term ? answer : null);
    // Search is external I/O; cancellation keeps an older answer out of this edit.
    $effect(() => {
        const query = term;
        if (choice || query.length < 2) return;
        const controller = new AbortController();
        const timer = setTimeout(async () => {
            try {
                const values = await searchGardenSpecies(query, controller.signal);
                if (!controller.signal.aborted) answer = { term: query, values, failed: false };
            } catch {
                if (!controller.signal.aborted) answer = { term: query, values: [], failed: true };
            }
        }, 200);
        return () => { clearTimeout(timer); controller.abort(); };
    });
</script>

<form class="space-y-2" onsubmit={(event) => { event.preventDefault(); if (choice && !busy) onsave(choice.species_id); }} data-garden-species-picker>
    <label class="block text-xs font-semibold">
        {$_('garden.rename.search', { default: 'Search animal species' })}
        <input class="input-base mt-1 min-h-11 w-full" maxlength="120" bind:value={input} oninput={() => { choice = null; }} disabled={busy} autocomplete="off" />
    </label>
    <p class="text-xs text-slate-500 dark:text-slate-400" aria-live="polite">
        {#if !choice}
            {#if term.length < 2}{$_('garden.rename.help', { default: 'Type at least two letters of a common or scientific name, then choose a species.' })}
            {:else if !current}{$_('common.loading', { default: 'Loading…' })}
            {:else if current.failed}{$_('garden.rename.search_failed', { default: 'Could not search species. Edit the search to try again.' })}
            {:else if !current.values.length}{$_('garden.rename.no_matches', { default: 'No matching animal species in the Garden catalogue.' })}{/if}
        {:else}{choice.scientific_name}{/if}
    </p>
    {#if !choice && current?.values.length}
        <ul class="max-h-40 overflow-y-auto rounded-lg border border-slate-200 p-1 dark:border-slate-700" aria-label={$_('garden.rename.matches', { default: 'Matching animal species' })}>
            {#each current.values as species (species.species_id)}
                <li><button type="button" class="btn btn-ghost min-h-11 w-full flex-col items-start px-2 text-left text-xs focus-ring" disabled={busy} onclick={() => { input = species.name; choice = species; }}>
                    <span class="break-words">{species.name}</span><span class="break-words font-normal italic">{species.scientific_name}</span>
                </button></li>
            {/each}
        </ul>
    {/if}
    <p class="text-xs text-slate-500 dark:text-slate-400">{$_('garden.rename.scope', { default: 'Changes this capture only. The original model result is kept in Details.' })}</p>
    <div class="flex flex-wrap gap-2">
        <button type="submit" class="btn btn-primary min-h-11 px-3 text-xs" disabled={busy || !choice}>{$_('garden.rename.save', { default: 'Save species' })}</button>
        <button type="button" class="btn btn-ghost min-h-11 px-3 text-xs" disabled={busy} onclick={oncancel}>{$_('common.cancel', { default: 'Cancel' })}</button>
    </div>
</form>
