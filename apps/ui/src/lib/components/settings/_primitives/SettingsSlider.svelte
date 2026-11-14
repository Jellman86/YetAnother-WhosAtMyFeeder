<script lang="ts">
    interface Props {
        id: string;
        label: string;
        description?: string;
        value: number;
        min: number;
        max: number;
        step: number;
        /** The value as people read it, shown beside the label and announced, e.g. "70%". */
        display: (value: number) => string;
        lowLabel?: string;
        highLabel?: string;
    }

    let { id, label, description, value = $bindable(), min, max, step, display, lowLabel, highLabel }: Props = $props();

    const shown = $derived(display(value));
    const descriptionId = $derived(description ? `${id}-desc` : undefined);
</script>

<!-- One slider row: label and value on one line, the slider and its end labels close beneath. -->
<div class="border-t border-line-soft pt-4 first:border-t-0 first:pt-0" data-settings-row data-settings-slider>
    <div class="flex items-baseline justify-between gap-3">
        <label for={id} class="min-w-0 text-sm font-semibold text-slate-900 dark:text-white">{label}</label>
        <output for={id} class="shrink-0 rounded-md bg-brand-700 px-2 py-0.5 text-xs font-bold tabular-nums text-white">{shown}</output>
    </div>
    {#if description}
        <p id={descriptionId} class="mt-1 text-sm leading-snug text-slate-600 dark:text-slate-300">{description}</p>
    {/if}
    <input
        {id}
        type="range"
        {min}
        {max}
        {step}
        bind:value
        aria-describedby={descriptionId}
        aria-valuetext={shown}
        class="mt-2 h-6 w-full cursor-pointer accent-brand-500 focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
    />
    {#if lowLabel || highLabel}
        <div class="flex justify-between gap-x-4 text-xs font-medium text-slate-600 dark:text-slate-300">
            <span>{lowLabel}</span>
            <span class="text-right">{highLabel}</span>
        </div>
    {/if}
</div>
