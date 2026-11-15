<script lang="ts">
    import { settingsFieldErrorLookup } from '../../../settings/field-error-context';
    import FieldRefusal from './FieldRefusal.svelte';

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
        /** The saved setting's API name, so a refused save marks this slider and says why. */
        field?: string;
    }

    let { id, label, description, value = $bindable(), min, max, step, display, lowLabel, highLabel, field }: Props = $props();

    const shown = $derived(display(value));
    const descriptionId = $derived(description ? `${id}-desc` : undefined);
    const fieldErrors = settingsFieldErrorLookup();
    const refusal = $derived(field ? fieldErrors?.errorFor(field) : undefined);
    const errorId = $derived(`${id}-error`);
    const describedByIds = $derived([descriptionId, refusal ? errorId : undefined].filter(Boolean).join(' ') || undefined);
</script>

<!-- One slider row, laid out like every other row: label and hint left; on the right the value as
     plain text, then the slider and its end labels. -->
<div class="settings-row space-y-3 md:grid md:settings-row-columns md:items-start md:gap-x-8 md:space-y-0" data-settings-row data-settings-slider>
    <div class="min-w-0">
        <label for={id} class="block text-base font-medium text-slate-900 dark:text-white">{label}</label>
        {#if description}
            <p id={descriptionId} class="mt-1 max-w-prose text-sm leading-snug text-slate-600 dark:text-slate-400">{description}</p>
        {/if}
    </div>
    <div class="min-w-0">
        <!-- For the eye only: the focused slider announces its value once, through aria-valuetext.
             An output element is a live region and would announce every change a second time. -->
        <p class="text-right text-sm font-semibold tabular-nums text-slate-900 dark:text-white" aria-hidden="true">{shown}</p>
        <input
            {id}
            type="range"
            {min}
            {max}
            {step}
            bind:value
            aria-describedby={describedByIds}
            aria-invalid={refusal && !refusal.conflict ? 'true' : undefined}
            aria-valuetext={shown}
            class="focus-ring mt-1 h-6 w-full cursor-pointer accent-brand-600"
        />
        {#if lowLabel || highLabel}
            <div class="flex justify-between gap-x-4 text-xs text-slate-600 dark:text-slate-400">
                <span>{lowLabel}</span>
                <span class="text-right">{highLabel}</span>
            </div>
        {/if}
        <FieldRefusal id={errorId} {refusal} />
    </div>
</div>
