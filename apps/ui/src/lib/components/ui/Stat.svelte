<script lang="ts">
    import { _ } from 'svelte-i18n';

    /**
     * One figure and its label, as a `<dt>`/`<dd>` pair: place it inside a `<dl>`. Only a reading
     * shows a number. A value that was not measured (null or undefined) says so in words, never as
     * a zero.
     */
    type Props = {
        label: string;
        value: string | number | null | undefined;
        unit?: string;
        /** A line under the figure: its window, its source, what it is out of. */
        detail?: string;
        size?: 'md' | 'lg';
        class?: string;
    };

    let { label, value, unit, detail, size = 'md', class: className = '' }: Props = $props();

    const measured = $derived(value !== null && value !== undefined && value !== '');
</script>

<div class="min-w-0 {className}">
    <dt class="text-sm font-semibold text-ink wrap-break-word">{label}</dt>
    <dd class="mt-1 wrap-break-word">
        {#if measured}
            <span class="figure text-strong {size === 'lg' ? 'text-3xl' : 'text-2xl'}">{value}</span>{#if unit}<span class="ml-1 text-xs text-muted">{unit}</span>{/if}
        {:else}
            <span class="text-sm font-medium text-muted">{$_('ui.state.not_measured', { default: 'Not measured' })}</span>
        {/if}
    </dd>
    {#if detail}
        <dd class="mt-1 text-xs text-muted wrap-break-word">{detail}</dd>
    {/if}
</div>
