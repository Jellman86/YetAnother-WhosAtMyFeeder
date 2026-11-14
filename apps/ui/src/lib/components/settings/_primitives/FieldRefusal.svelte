<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { SettingsFieldError } from '../../../settings/field-errors';

    // The reason a save refused a field, shown under the input; the input names `id` in its
    // aria-describedby and sets aria-invalid while `refusal` is set.
    let { id, refusal }: { id: string; refusal: SettingsFieldError | undefined } = $props();
</script>

{#if refusal}
    <p {id} class="mt-1.5 text-xs font-semibold text-red-700 dark:text-red-300" data-field-error={refusal.field}>{$_(refusal.key, { values: refusal.values, default: refusal.fallback })}</p>
{/if}
