<script lang="ts">
    /**
     * Two pictures laid one over the other, so a row says "more than one" at thumbnail size.
     * Heard bands layer spectrograms; a capture with several species layers its crops. One picture
     * stands alone, and none keeps the same footprint with a placeholder, so rows never shift.
     */
    interface Props {
        sources: string[];
        /** Spectrograms are zoomed onto the band where birdsong sits; the top is always silence. */
        spectrogram?: boolean;
        size?: 'row' | 'card';
    }
    let { sources, spectrogram = false, size = 'row' }: Props = $props();
    let failed = $state<Record<string, true>>({});
    const shown = $derived(sources.filter((source) => !failed[source]).slice(0, 2));
    const tile = $derived(size === 'card' ? 'h-14 w-14' : 'h-9 w-9');
</script>

<span class="relative block shrink-0 {size === 'card' ? 'h-16 w-16' : 'h-11 w-11'}" aria-hidden="true" data-layered-thumbs={shown.length}>
    {#if shown.length === 0}
        <span class="flex h-full w-full items-center justify-center rounded-lg bg-slate-100 text-slate-400 ring-1 ring-slate-200 dark:bg-slate-800 dark:text-slate-500 dark:ring-slate-700">
            <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8"><path stroke-linecap="round" stroke-linejoin="round" d="M4 12v2m4-5v8m4-13v16m4-13v10m4-7v4" /></svg>
        </span>
    {:else if shown.length === 1}
        <span class="block h-full w-full overflow-hidden rounded-lg bg-slate-100 ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700">
            <img src={shown[0]} alt="" loading="lazy" class="h-full w-full object-cover {spectrogram ? 'scale-[1.6] [transform-origin:50%_64%]' : ''}" onerror={() => (failed = { ...failed, [shown[0]]: true })} />
        </span>
    {:else}
        {#each shown as source, index (source)}
            <span class="absolute {tile} overflow-hidden rounded-md bg-slate-100 ring-1 ring-slate-200 dark:bg-slate-800 dark:ring-slate-700 {index === 0 ? 'left-0 top-0' : 'bottom-0 right-0 outline outline-2 outline-white dark:outline-slate-950'}">
                <img src={source} alt="" loading="lazy" class="h-full w-full object-cover {spectrogram ? 'scale-[1.6] [transform-origin:50%_64%]' : ''}" onerror={() => (failed = { ...failed, [source]: true })} />
            </span>
        {/each}
    {/if}
</span>
