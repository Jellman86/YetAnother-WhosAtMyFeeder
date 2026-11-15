<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { SettingsFieldError } from '../../../settings/field-errors';

    // The reason a save refused a field, shown under the input; the input names `id` in its
    // aria-describedby and sets aria-invalid while `refusal` is set. A conflict is not invalid,
    // so it is worded as a choice to make and not shown in red.
    let { id, refusal }: { id: string; refusal: SettingsFieldError | undefined } = $props();
</script>

{#if refusal}
    <p {id} class="mt-1.5 text-xs font-semibold {refusal.conflict ? 'text-attention-800 dark:text-attention-200' : 'text-red-700 dark:text-red-300'}" data-field-error={refusal.field} data-field-conflict={refusal.conflict ? refusal.field : undefined}>{$_(refusal.key, { values: refusal.values, default: refusal.fallback })}</p>
{/if}
