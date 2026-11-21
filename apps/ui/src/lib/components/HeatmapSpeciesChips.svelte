<script lang="ts">
    import { _ } from 'svelte-i18n';

    /**
     * The row above a weekday-by-hour grid that shows one species' pattern instead of all species':
     * "when does the Robin come?" is the question the all-species grid cannot answer. The Leaderboard
     * and Audio History share it, so the choice looks and behaves the same on both. It shows only when
     * there is more than one species to choose between; a single species is already the whole grid.
     */
    type Option = { key: string; label: string };

    type Props = {
        options: readonly Option[];
        /** The chosen species' key, or null for all species. */
        selected: string | null;
        /** What the row chooses, for a screen reader. */
        label: string;
        onselect: (key: string | null) => void;
        [data: `data-${string}`]: string | boolean | undefined;
    };

    let { options, selected, label, onselect, ...data }: Props = $props();
</script>

{#if options.length > 1}
    <div class="-mx-1 mt-3 flex gap-1 overflow-x-auto px-1 pb-1 sm:flex-wrap sm:overflow-visible" role="group" aria-label={label} {...data}>
        <button type="button" class="btn btn-ghost min-h-11 shrink-0 whitespace-nowrap px-2.5 text-xs {selected === null ? 'bg-surface-raised font-semibold text-strong' : ''}" aria-pressed={selected === null} onclick={() => onselect(null)}>
            {$_('leaderboard.heatmap_all_species', { default: 'All species' })}
        </button>
        {#each options as option, index (`${option.key}|${index}`)}
            <button type="button" class="btn btn-ghost min-h-11 shrink-0 whitespace-nowrap px-2.5 text-xs {selected === option.key ? 'bg-surface-raised font-semibold text-strong' : ''}" aria-pressed={selected === option.key} onclick={() => onselect(option.key)}>
                {option.label}
            </button>
        {/each}
    </div>
{/if}
