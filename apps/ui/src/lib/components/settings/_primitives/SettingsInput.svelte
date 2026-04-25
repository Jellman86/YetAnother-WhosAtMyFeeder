<script lang="ts">
    interface Props {
        id: string;
        type?: 'text' | 'number' | 'url' | 'password' | 'email';
        value: string | number;
        placeholder?: string;
        ariaLabel?: string;
        autocomplete?: string;
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
        autocomplete,
        min,
        max,
        step,
        disabled = false,
        oninput,
        onkeydown
    }: Props = $props();
</script>

<input
    {id}
    {type}
    {placeholder}
    {disabled}
    autocomplete={autocomplete as any}
    {min}
    {max}
    {step}
    aria-label={ariaLabel}
    value={value as any}
    oninput={(e) => oninput?.((e.currentTarget as HTMLInputElement).value)}
    onkeydown={(e) => onkeydown?.(e)}
    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white font-bold text-sm focus:ring-2 focus:ring-teal-500 outline-none transition-all disabled:opacity-50 disabled:cursor-not-allowed"
/>
