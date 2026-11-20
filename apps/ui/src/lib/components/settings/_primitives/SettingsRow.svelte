<script lang="ts">
    import type { Snippet } from 'svelte';

    interface Props {
        label: string;
        description?: string;
        labelId?: string;
        descriptionId?: string;
        /**
         * `inline` and `stacked` (the default and its old name): label and hint left, the control
         * right from 768px, stacked on a phone. `block`: the control takes the row's full width
         * under its label, for lists and anything wider than the control column.
         */
        layout?: 'inline' | 'stacked' | 'block';
        children: Snippet;
    }

    let { label, description, labelId, descriptionId, layout = 'inline', children }: Props = $props();
    const wide = $derived(layout === 'block');
</script>

<!-- One row pattern for every setting: label, a hint that says what it does, then the control.
     The label is the one semibold thing in a row; the hint is smaller, muted and regular.
     The section's card draws the hairline between rows; a row never boxes itself. -->
<div
    class="settings-row space-y-3 {wide ? '' : 'md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0'}"
    data-settings-row
>
    <div id={labelId} class="min-w-0">
        <span class="block text-base font-semibold text-strong" data-settings-row-label>{label}</span>
        {#if description}
            <span id={descriptionId} class="mt-1 block max-w-prose text-sm leading-snug text-muted">
                {description}
            </span>
        {/if}
    </div>
    <div class="min-w-0">
        {@render children()}
    </div>
</div>
