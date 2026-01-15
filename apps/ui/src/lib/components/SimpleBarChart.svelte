<script lang="ts">
    import { _ } from 'svelte-i18n';

    interface Props {
        data: number[];
        labels: string[];
        title: string;
        color?: string;
        showEveryNthLabel?: number;  // For dense charts like hourly, only show every Nth label
        onclick?: (index: number) => void;  // Optional click handler for bars
    }

    let { data, labels, title, color = 'bg-teal-500', showEveryNthLabel, onclick }: Props = $props();

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

<div class="w-full overflow-hidden">
    <div class="flex items-center justify-between mb-2">
        <h4 class="text-sm font-medium text-slate-700 dark:text-slate-300">{title}</h4>
        <span class="text-xs text-slate-400 dark:text-slate-500">{total} total</span>
    </div>

    <!-- Chart container with proper overflow handling -->
    <div class="relative" role="img" aria-label={title}>
        <!-- Bars -->
        <div class="flex items-end gap-px h-28">
            {#each data as value, i}
                <div
                    class="flex-1 min-w-0 flex flex-col items-center justify-end h-full relative cursor-pointer"
                    onmouseenter={() => hoveredIndex = i}
                    onmouseleave={() => hoveredIndex = null}
                    onfocus={() => hoveredIndex = i}
                    onblur={() => hoveredIndex = null}
                    onclick={() => onclick?.(i)}
                    onkeydown={(e) => {
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            onclick?.(i);
                        }
                    }}
                    role="button"
                    tabindex="0"
                    aria-label="{labels[i]}: {value} {$_('common.detections', { default: 'detections' })}"
                >
                    <!-- Tooltip - positioned above with proper z-index -->
                    {#if hoveredIndex === i}
                        <div class="absolute -top-7 left-1/2 -translate-x-1/2 px-2 py-1 rounded-md
                                    bg-slate-900 dark:bg-slate-700 text-white text-xs font-medium
                                    whitespace-nowrap z-20 shadow-lg pointer-events-none
                                    before:content-[''] before:absolute before:top-full before:left-1/2
                                    before:-translate-x-1/2 before:border-4 before:border-transparent
                                    before:border-t-slate-900 dark:before:border-t-slate-700">
                            {labels[i]}: {value}
                        </div>
                    {/if}

                    <!-- Bar -->
                    <div
                        class="w-full rounded-sm transition-all duration-150 {hoveredIndex === i ? 'ring-2 ring-teal-400 ring-offset-1' : ''}"
                        class:bg-teal-500={value > 0 && hoveredIndex !== i}
                        class:bg-teal-400={value > 0 && hoveredIndex === i}
                        class:bg-slate-200={value === 0}
                        class:dark:bg-slate-600={value === 0}
                        style="height: {value > 0 ? Math.max((value / maxValue) * 100, 8) : 4}%"
                    ></div>
                </div>
            {/each}
        </div>

        <!-- Labels row - separate for better control -->
        <div class="flex mt-1.5 overflow-hidden">
            {#each labels as label, i}
                <div class="flex-1 min-w-0 text-center">
                    {#if shouldShowLabel(i)}
                        <span class="text-[9px] leading-none text-slate-500 dark:text-slate-400
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
            <caption>{title}</caption>
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
