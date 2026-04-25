<script lang="ts">
    interface Props {
        id: string;
        value: string;
        rows?: number;
        placeholder?: string;
        ariaLabel?: string;
        font?: 'sans' | 'mono';
        oninput: (next: string) => void;
    }

    let { id, value, rows = 6, placeholder, ariaLabel, font = 'sans', oninput }: Props = $props();
</script>

<textarea
    {id}
    {rows}
    {placeholder}
    aria-label={ariaLabel}
    value={value}
    oninput={(e) => oninput((e.currentTarget as HTMLTextAreaElement).value)}
    class="w-full px-4 py-3 rounded-2xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 text-slate-900 dark:text-white {font === 'mono' ? 'font-mono text-xs' : 'text-sm'} transition-colors focus:ring-2 focus:ring-offset-2 focus:ring-teal-500 dark:focus:ring-offset-slate-900 outline-none"
></textarea>
