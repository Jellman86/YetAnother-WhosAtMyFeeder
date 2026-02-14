<script lang="ts">
    import { _ } from 'svelte-i18n';
</script>

<span
    class="inline-flex items-center gap-1 rounded-full border border-emerald-200/80 bg-emerald-50 px-2 py-0.5 text-[9px] font-black uppercase tracking-widest text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/20 dark:text-emerald-300"
>
    <svg class="h-2.5 w-2.5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M5 13l4 4L19 7" />
    </svg>
    {$_('common.saved')}
</span>
