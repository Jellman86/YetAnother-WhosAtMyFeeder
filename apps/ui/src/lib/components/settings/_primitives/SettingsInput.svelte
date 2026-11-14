<script lang="ts">
    import type { HTMLInputAttributes } from 'svelte/elements';
    import { settingsFieldErrorLookup } from '../../../settings/field-error-context';
    import FieldRefusal from './FieldRefusal.svelte';

    interface Props {
        id: string;
        type?: 'text' | 'number' | 'url' | 'password' | 'email';
        value: string | number;
        placeholder?: string;
        ariaLabel?: string;
        /** Id of the help or unit text read after the field's name. */
        describedBy?: string;
        /** Marks the value as rejected; the reason must be in the text `describedBy` names. */
        invalid?: boolean;
        /**
         * The saved setting this input edits, as the save sends it. A save that refuses it marks
         * the input and shows the reason under it until the value changes.
         */
        field?: string;
        autocomplete?: HTMLInputAttributes['autocomplete'];
        min?: number;
        max?: number;
        step?: number;
        disabled?: boolean;
        oninput?: (next: string) => void;
        onkeydown?: (e: KeyboardEvent) => void;
    }

    let {
        id,
        type = 'text',
        value,
        placeholder,
        ariaLabel,
        describedBy,
        invalid = false,
        field,
        autocomplete,
        min,
        max,
        step,
        disabled = false,
        oninput,
        onkeydown
    }: Props = $props();

    const fieldErrors = settingsFieldErrorLookup();
    const refusal = $derived(field ? fieldErrors?.errorFor(field) : undefined);
    const errorId = $derived(`${id}-error`);
    const describedByIds = $derived([describedBy, refusal ? errorId : undefined].filter(Boolean).join(' ') || undefined);
</script>

<input
    {id}
    {type}
    {placeholder}
    {disabled}
    {autocomplete}
    {min}
    {max}
    {step}
    aria-label={ariaLabel}
    aria-describedby={describedByIds}
    aria-invalid={invalid || refusal ? 'true' : undefined}
    {value}
    oninput={(e) => oninput?.((e.currentTarget as HTMLInputElement).value)}
    onkeydown={(e) => onkeydown?.(e)}
    class="w-full px-4 py-3 rounded-2xl border bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-brand-500 outline-hidden transition-all disabled:opacity-50 disabled:cursor-not-allowed
           {refusal ? 'border-red-600 dark:border-red-400' : 'border-slate-200 dark:border-slate-700'}"
/>
<FieldRefusal id={errorId} {refusal} />
