<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';

    interface Props {
        // Stable identifier — kept for backwards compatibility with existing
        // callsites and for aria/test hooks. Open/closed state is no longer
        // persisted; callsites can opt into an initially open state when work is
        // already running inside the disclosure.
        id?: string;
        title?: string;
        description?: string;
        openByDefault?: boolean;
        children: Snippet;
    }

    let { id, title, description, openByDefault = false, children }: Props = $props();

    let userOpen = $state<boolean | null>(null);
    const open = $derived(userOpen ?? openByDefault);
    const contentId = $derived(id ? `${id}-content` : undefined);
</script>

<div class="rounded-2xl border border-dashed border-slate-200 dark:border-slate-700/60 bg-slate-50/40 dark:bg-slate-900/30">
    <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onclick={() => (userOpen = !open)}
        class="flex min-h-11 w-full cursor-pointer items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-teal-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
    >
        <span class="flex min-w-0 items-center gap-2">
            <span class="rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-0.5 text-xs font-black uppercase tracking-wide text-amber-700 dark:text-amber-300">
                {$_('settings.common.advanced', { default: 'Advanced' })}
            </span>
            <span class="text-sm font-bold text-slate-700 dark:text-slate-200">
                {title ?? $_('settings.common.advanced_default_title', { default: 'Advanced options' })}
            </span>
        </span>
        <svg
            class="w-4 h-4 text-slate-400 transition-transform duration-200 {open ? 'rotate-180' : ''}"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            aria-hidden="true"
        >
            <polyline points="6 9 12 15 18 9"/>
        </svg>
    </button>
    {#if open}
        <div id={contentId} class="space-y-4 px-4 pb-4 pt-1">
            {#if description}
                <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-400">{description}</p>
            {/if}
            {@render children()}
        </div>
    {/if}
</div>
