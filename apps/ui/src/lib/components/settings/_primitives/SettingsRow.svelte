<script lang="ts">
    import type { Snippet } from 'svelte';

    interface Props {
        label: string;
        description?: string;
        // When provided, used to associate the label with the control via
        // aria-labelledby; required for switches/buttons that don't have a
        // wrapping <label>.
        labelId?: string;
        // Layout: side-by-side (default) puts the control on the right; stacked
        // puts the control under the label/description (used for things that
        // can't sensibly fit on one line, e.g. multi-button segmented controls).
        layout?: 'inline' | 'stacked';
        children: Snippet;
    }

    let { label, description, labelId, layout = 'inline', children }: Props = $props();
</script>

<div
    class="p-4 rounded-2xl bg-slate-50 dark:bg-slate-900/50 border border-slate-100 dark:border-slate-700/50
           {layout === 'inline' ? 'flex items-center justify-between gap-4' : 'flex flex-col gap-3'}"
>
    <div id={labelId} class="min-w-0">
        <span class="block text-sm font-bold text-slate-900 dark:text-white">{label}</span>
        {#if description}
            <span class="block text-[11px] text-slate-500 dark:text-slate-400 font-medium leading-snug mt-0.5">
                {description}
            </span>
        {/if}
    </div>
    <div class="{layout === 'inline' ? 'flex-shrink-0' : 'w-full'}">
        {@render children()}
    </div>
</div>
