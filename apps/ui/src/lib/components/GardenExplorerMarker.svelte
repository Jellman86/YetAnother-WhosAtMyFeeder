<script lang="ts">
    /**
     * The worded "Garden" marker on every Garden entry, so an animal is never read as a bird
     * record. Words, not only a colour or an icon (WCAG 1.4.1).
     */
    import { _ } from 'svelte-i18n';

    /** `compact` sits in a line of small text, as a row's second line. */
    let { overlay = false, compact = false }: { overlay?: boolean; compact?: boolean } = $props();
</script>

<span
    class="inline-flex shrink-0 items-center gap-1 rounded-full border font-bold {compact ? 'px-1.5 text-3xs' : 'px-2 py-0.5 text-2xs'} {overlay
        ? 'border-white/10 bg-black/60 text-white backdrop-blur-md'
        : 'border-line bg-surface-raised text-slate-700 dark:text-slate-200'}"
    data-garden-marker
>
    <svg class="h-3 w-3" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <circle cx="6" cy="10" r="2.2" /><circle cx="10" cy="5.5" r="2.2" /><circle cx="14" cy="5.5" r="2.2" /><circle cx="18" cy="10" r="2.2" />
        <path d="M12 11c-3 0-6 4.2-6 6.5 0 1.6 1.3 2.5 3 2.5 1.2 0 2-.6 3-.6s1.8.6 3 .6c1.7 0 3-.9 3-2.5 0-2.3-3-6.5-6-6.5z" />
    </svg>
    {$_('garden.explorer.marker', { default: 'Garden' })}
</span>
