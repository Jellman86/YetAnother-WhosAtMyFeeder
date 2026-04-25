<script lang="ts" generics="T extends string">
    interface Option {
        value: T;
        label: string;
    }

    interface Props {
        id: string;
        value: T;
        options: Option[];
        ariaLabel?: string;
        onchange: (next: T) => void;
        disabled?: boolean;
    }

    let { id, value, options, ariaLabel, onchange, disabled = false }: Props = $props();
</script>

<select
    {id}
    {value}
    {disabled}
    aria-label={ariaLabel}
    onchange={(e) => onchange(e.currentTarget.value as T)}
    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
>
    {#each options as opt}
        <option value={opt.value}>{opt.label}</option>
    {/each}
</select>
