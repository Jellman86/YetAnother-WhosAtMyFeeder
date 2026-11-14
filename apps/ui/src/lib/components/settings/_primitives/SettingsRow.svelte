<script lang="ts">
    import type { Snippet } from 'svelte';

    interface Props {
        label: string;
        description?: string;
        // When provided, used to associate the label with the control via
        // aria-labelledby; required for switches/buttons that don't have a
        // wrapping <label>.
        labelId?: string;
        // Lets a control reference the description via aria-describedby.
        descriptionId?: string;
        // Layout: side-by-side (default) puts the control on the right; stacked
        // puts the control under the label/description (used for things that
        // can't sensibly fit on one line, e.g. multi-button segmented controls).
        layout?: 'inline' | 'stacked';
        children: Snippet;
    }

    let { label, description, labelId, descriptionId, layout = 'inline', children }: Props = $props();
</script>

<!-- One row pattern for every setting: label, a hint that says what it does, then the control.
     Rows are separated by a hairline inside their card, never boxed inside it. -->
<div
    class="settings-row border-t border-line-soft pt-4 first:border-t-0 first:pt-0
           {layout === 'inline' ? 'flex items-center justify-between gap-4' : 'flex flex-col gap-3'}"
    data-settings-row
>
    <div id={labelId} class="min-w-0">
        <span class="block text-sm font-semibold text-slate-900 dark:text-white">{label}</span>
        {#if description}
            <span id={descriptionId} class="mt-1 block text-sm leading-snug text-slate-600 dark:text-slate-300">
                {description}
            </span>
        {/if}
    </div>
    <div class="{layout === 'inline' ? 'shrink-0' : 'w-full'}">
        {@render children()}
    </div>
</div>
