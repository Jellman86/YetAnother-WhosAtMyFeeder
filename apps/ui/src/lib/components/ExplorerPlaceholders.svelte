<script lang="ts">
    /**
     * The Explorer's first read, drawn in the anatomy and size of the cards or rows it will hold,
     * so nothing jumps when they arrive and no count or empty state is claimed before it is known.
     * The parent supplies the real grid or list container; these are only its items. Each block
     * pulses, and stands still under reduced motion.
     */
    let { view, count = view === 'cards' ? 6 : 8 }: { view: 'cards' | 'list'; count?: number } = $props();

    const pulse = 'bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60';
    // Varied name widths read as a list of names rather than a barcode.
    const nameWidths = ['w-2/3', 'w-1/2', 'w-3/5', 'w-2/5'];
</script>

{#each Array.from({ length: count }, (_, index) => index) as index (index)}
    {#if view === 'cards'}
        <div
            class="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-slate-200/80 bg-white/90 shadow-sm dark:border-slate-700/60 dark:bg-slate-800/75"
            aria-hidden="true"
            data-explorer-placeholder="card"
        >
            <div class="aspect-[4/3] {pulse}" data-loading-placeholder></div>
            <div class="flex flex-1 flex-col gap-2.5 p-4">
                <div class="space-y-1.5">
                    <div class="h-5 {nameWidths[index % nameWidths.length]} rounded {pulse}" data-loading-placeholder></div>
                    <div class="h-3 w-1/3 rounded {pulse}" data-loading-placeholder></div>
                </div>
                <div class="h-3 w-1/4 rounded {pulse}" data-loading-placeholder></div>
                <div class="mt-auto h-2.5 w-1/2 rounded {pulse}" data-loading-placeholder></div>
            </div>
        </div>
    {:else}
        <div
            class="grid min-h-14 grid-cols-[4rem_2.75rem_minmax(0,1fr)_auto] items-center gap-3 px-3"
            aria-hidden="true"
            data-explorer-placeholder="row"
        >
            <div class="space-y-1 py-2">
                <div class="h-3.5 w-10 rounded {pulse}" data-loading-placeholder></div>
                <div class="h-2.5 w-8 rounded {pulse}" data-loading-placeholder></div>
            </div>
            <div class="flex justify-center"><div class="h-9 w-9 rounded-lg {pulse}" data-loading-placeholder></div></div>
            <div class="min-w-0 space-y-1.5 py-2">
                <div class="h-3.5 max-w-full {nameWidths[index % nameWidths.length]} rounded {pulse}" data-loading-placeholder></div>
                <div class="h-2.5 w-24 max-w-full rounded {pulse}" data-loading-placeholder></div>
            </div>
            <div class="h-3.5 w-9 rounded {pulse}" data-loading-placeholder></div>
        </div>
    {/if}
{/each}
