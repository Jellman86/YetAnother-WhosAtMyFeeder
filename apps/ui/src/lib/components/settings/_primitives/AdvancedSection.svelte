<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { onMount } from 'svelte';

    interface Props {
        // Stable identifier — used as the localStorage key so each Advanced
        // block remembers its own open/closed state.
        id: string;
        title?: string;
        description?: string;
        children: Snippet;
    }

    let { id, title, description, children }: Props = $props();

    const storageKey = $derived(`yawamf:settings:advanced:${id}`);
    let open = $state(false);

    onMount(() => {
        try {
            open = window.localStorage.getItem(storageKey) === '1';
        } catch {
            open = false;
        }
    });

    function persist(next: boolean) {
        open = next;
        try {
            window.localStorage.setItem(storageKey, next ? '1' : '0');
        } catch {
            // localStorage can be disabled in private mode — silently degrade.
        }
    }
</script>

<div class="rounded-2xl border border-dashed border-slate-200 dark:border-slate-700/60 bg-slate-50/40 dark:bg-slate-900/30">
    <button
        type="button"
        aria-expanded={open}
        onclick={() => persist(!open)}
        class="w-full flex items-center justify-between gap-3 px-4 py-3 rounded-2xl text-left focus:outline-none focus:ring-2 focus:ring-teal-400"
    >
        <div class="flex items-center gap-2 min-w-0">
            <span class="px-2 py-0.5 rounded-md bg-amber-500/10 border border-amber-500/30 text-[9px] font-black uppercase tracking-widest text-amber-700 dark:text-amber-300">
                {$_('settings.common.advanced', { default: 'Advanced' })}
            </span>
            <span class="text-sm font-bold text-slate-700 dark:text-slate-200 truncate">
                {title ?? $_('settings.common.advanced_default_title', { default: 'Advanced options' })}
            </span>
        </div>
        <svg
            class="w-4 h-4 text-slate-400 transition-transform duration-200 {open ? 'rotate-180' : ''}"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            aria-hidden="true"
        >
            <polyline points="6 9 12 15 18 9"/>
        </svg>
    </button>
    {#if open}
        <div class="px-4 pb-4 pt-1 space-y-4">
            {#if description}
                <p class="text-[11px] text-slate-500 dark:text-slate-400 leading-snug">{description}</p>
            {/if}
            {@render children()}
        </div>
    {/if}
</div>
