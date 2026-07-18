<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        data: number[];
        labels: string[];
        title: string;
        ariaLabel?: string;
        showEveryNthLabel?: number;  // For dense charts like hourly, only show every Nth label
        onclick?: (index: number) => void;  // Optional click handler for bars
    }

    let { data, labels, title, ariaLabel, showEveryNthLabel, onclick }: Props = $props();

    let maxValue = $derived(Math.max(...data, 1));
    let total = $derived(data.reduce((a, b) => a + b, 0));
    let hoveredIndex = $state<number | null>(null);

    // Auto-calculate label interval if not provided
    let labelInterval = $derived(() => {
        if (showEveryNthLabel) return showEveryNthLabel;
        if (data.length > 12) return Math.ceil(data.length / 6);  // Show ~6 labels for many items
        return 1;  // Show all labels for fewer items
    });

    function shouldShowLabel(index: number): boolean {
        const interval = labelInterval();
        if (interval === 1) return true;
        // Always show first, last, and every Nth
        if (index === 0 || index === data.length - 1) return true;
        return index % interval === 0;
    }
</script>

{#snippet barContent(value: number, i: number)}
    {#if hoveredIndex === i}
        <div class="absolute -top-7 left-1/2 z-20 -translate-x-1/2 whitespace-nowrap rounded-md bg-slate-900 px-2 py-1 text-xs font-medium text-white shadow-lg pointer-events-none before:absolute before:left-1/2 before:top-full before:-translate-x-1/2 before:border-4 before:border-transparent before:border-t-slate-900 dark:bg-slate-700 dark:before:border-t-slate-700">
            {labels[i]}: {value}
        </div>
    {/if}

    <div
        class="w-full rounded-sm transition-all duration-150 {hoveredIndex === i ? 'ring-2 ring-teal-400 ring-offset-1' : ''}"
        class:bg-teal-500={value > 0 && hoveredIndex !== i}
        class:bg-teal-400={value > 0 && hoveredIndex === i}
        class:bg-slate-200={value === 0}
        class:dark:bg-slate-600={value === 0}
        style="height: {value > 0 ? Math.max((value / maxValue) * 100, 8) : 4}%"
    ></div>
{/snippet}

<div class="w-full overflow-hidden">
    <div class="mb-2 flex items-center {title ? 'justify-between' : 'justify-end'}">
        {#if title}
            <h4 class="text-sm font-medium text-slate-700 dark:text-slate-300">{title}</h4>
        {/if}
        <span class="text-xs text-slate-400 dark:text-slate-500">{total} total</span>
    </div>

    <!-- Chart container with proper overflow handling -->
    <div class="relative" role="img" aria-label={ariaLabel || title}>
        <!-- Bars -->
        <div class="flex items-end gap-px h-28">
            {#each data as value, i}
                {#if onclick}
                    <button
                        type="button"
                        class="relative flex h-full min-w-0 flex-1 cursor-pointer flex-col items-center justify-end"
                        onmouseenter={() => hoveredIndex = i}
                        onmouseleave={() => hoveredIndex = null}
                        onfocus={() => hoveredIndex = i}
                        onblur={() => hoveredIndex = null}
                        onclick={() => onclick(i)}
                        aria-label="{labels[i]}: {value} {$_('common.detections', { default: 'detections' })}"
                    >
                        {@render barContent(value, i)}
                    </button>
                {:else}
                    <div
                        class="relative flex h-full min-w-0 flex-1 flex-col items-center justify-end"
                        onmouseenter={() => hoveredIndex = i}
                        onmouseleave={() => hoveredIndex = null}
                        role="presentation"
                    >
                        {@render barContent(value, i)}
                    </div>
                {/if}
            {/each}
        </div>

        <!-- Labels row - separate for better control -->
        <div class="flex mt-1.5 overflow-hidden">
            {#each labels as label, i}
                <div class="flex-1 min-w-0 text-center">
                    {#if shouldShowLabel(i)}
                        <span class="text-xs leading-none text-slate-500 dark:text-slate-400
                                     {hoveredIndex === i ? 'text-slate-700 dark:text-slate-300 font-medium' : ''}">
                            {label}
                        </span>
                    {/if}
                </div>
            {/each}
        </div>
    </div>

    <!-- Screen reader accessible table alternative -->
    <div class="sr-only">
        <table>
            <caption>{ariaLabel || title}</caption>
            <thead>
                <tr>
                    <th>{$_('common.period', { default: 'Period' })}</th>
                    <th>{$_('common.detections', { default: 'Detections' })}</th>
                </tr>
            </thead>
            <tbody>
                {#each data as value, i}
                    <tr>
                        <td>{labels[i]}</td>
                        <td>{value}</td>
                    </tr>
                {/each}
            </tbody>
        </table>
    </div>
</div>
