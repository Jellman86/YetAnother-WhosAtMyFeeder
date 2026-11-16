<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';

    /**
     * A chart with its words beside it. A canvas says nothing to a screen reader, and a colour
     * named only on hover says nothing to anyone else, so every chart carries a key that names each
     * colour with its figure, a table of the data it draws, or both (ui-ux.md, "A chart's colours
     * are named in words beside it").
     */
    type KeyItem = {
        label: string;
        /** The figure for this series, as the chart's reader would say it. */
        value?: string;
        /** The swatch's fill class, the same one the chart draws the series with. */
        swatch: string;
    };
    type DataTable = {
        columns: string[];
        rows: (string | number)[][];
    };
    /**
     * At least one way to say the chart in words: a key of swatches, a key the caller draws (for
     * line samples with dashes, say), or a table of the data.
     */
    type Words =
        | { key: KeyItem[]; legend?: Snippet; table?: DataTable }
        | { key?: KeyItem[]; legend: Snippet; table?: DataTable }
        | { key?: KeyItem[]; legend?: Snippet; table: DataTable };

    type Props = Words & {
        title: string;
        description?: string;
        headingLevel?: 2 | 3 | 4;
        /** The title is for assistive technology only, where a heading above already names the chart. */
        hideTitle?: boolean;
        /** The chart. It gives itself its own role and label (a canvas or svg as role="img"). */
        children: Snippet;
        class?: string;
    };

    let { title, description, headingLevel = 3, hideTitle = false, children, key, legend, table, class: className = '' }: Props = $props();

    const titleId = $props.id();
</script>

<figure class="min-w-0 {className}" aria-labelledby={titleId}>
    <figcaption class={hideTitle && !description ? 'sr-only' : ''}>
        <svelte:element this={`h${headingLevel}`} id={titleId} class="text-sm font-semibold text-strong wrap-break-word {hideTitle ? 'sr-only' : ''}">{title}</svelte:element>
        {#if description}
            <p class="mt-1 text-xs text-muted">{description}</p>
        {/if}
    </figcaption>
    <div class="min-w-0 {hideTitle && !description ? '' : 'mt-3'}">
        {@render children()}
    </div>
    {#if legend}
        <div class="mt-3">{@render legend()}</div>
    {/if}
    {#if key && key.length > 0}
        <ul class="mt-3 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label={$_('ui.chart.key', { default: 'Key' })}>
            {#each key as item (item.label)}
                <li class="inline-flex min-w-0 items-center gap-1.5">
                    <span class="h-2.5 w-2.5 shrink-0 rounded-sm {item.swatch}" aria-hidden="true"></span>
                    <span class="text-ink wrap-break-word">{item.label}</span>
                    {#if item.value}
                        <span class="font-semibold tabular-nums text-strong">{item.value}</span>
                    {/if}
                </li>
            {/each}
        </ul>
    {/if}
    {#if table}
        <details class="group mt-2">
            <summary class="inline-flex min-h-11 cursor-pointer list-none items-center gap-1.5 rounded-lg text-xs font-semibold text-accent-ink focus-ring">
                <svg class="h-3.5 w-3.5 transition-transform group-open:rotate-90" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <path d="M6 4l4 4-4 4" />
                </svg>
                {$_('ui.chart.show_data', { default: 'Show the data as a table' })}
            </summary>
            <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
            <!-- A long record scrolls in its own box, which a keyboard has to be able to reach. -->
            <div class="mt-2 max-h-80 overflow-auto rounded-lg focus-ring" tabindex="0" role="region" aria-label={title}>
                <table class="w-full text-left text-xs">
                    <caption class="sr-only">{title}</caption>
                    <thead class="sticky top-0 bg-surface">
                        <tr class="border-b border-line-soft">
                            {#each table.columns as column (column)}
                                <th scope="col" class="py-1.5 pr-4 font-semibold text-muted">{column}</th>
                            {/each}
                        </tr>
                    </thead>
                    <tbody class="divide-y divide-line-soft">
                        {#each table.rows as row, rowIndex (rowIndex)}
                            <tr>
                                {#each row as cell, cellIndex (cellIndex)}
                                    <td class="py-1.5 pr-4 tabular-nums text-ink">{cell}</td>
                                {/each}
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        </details>
    {/if}
</figure>
