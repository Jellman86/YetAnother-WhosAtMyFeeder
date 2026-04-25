<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';

    interface Props {
        title: string;
        subtitle?: string;
        loading?: boolean;
        // Inline status message (e.g. save success / save error).
        message?: { type: 'success' | 'error'; text: string } | null;
        onRefresh?: () => void;
        refreshing?: boolean;
        // Dirty/save bar — when isDirty is true the sticky footer renders.
        isDirty?: boolean;
        saving?: boolean;
        onSave?: () => void;
        // Tab strip lives between the header and the body so it stays in
        // tab-order for keyboard users.
        tabs?: Snippet;
        children: Snippet;
    }

    let {
        title,
        subtitle,
        loading = false,
        message = null,
        onRefresh,
        refreshing = false,
        isDirty = false,
        saving = false,
        onSave,
        tabs,
        children
    }: Props = $props();
</script>

<div class="max-w-4xl mx-auto space-y-8 pb-20">
    <header class="flex items-center justify-between">
        <div>
            <h2 class="text-3xl font-black text-slate-900 dark:text-white tracking-tight">{title}</h2>
            {#if subtitle}
                <p class="text-sm text-slate-500 dark:text-slate-400 font-medium">{subtitle}</p>
            {/if}
        </div>
        {#if onRefresh}
            <button
                type="button"
                onclick={() => onRefresh?.()}
                disabled={refreshing}
                class="btn btn-secondary px-4 py-2 text-sm font-bold"
                aria-label={$_('common.refresh')}
            >
                <svg class="w-4 h-4 {refreshing ? 'animate-spin' : ''}" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                </svg>
                {$_('common.refresh')}
            </button>
        {/if}
    </header>

    {#if message}
        <div
            role="status"
            class="p-4 rounded-2xl animate-in slide-in-from-top-2 {message.type === 'success'
                ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-400 border border-emerald-500/20'
                : 'bg-red-500/10 text-red-700 dark:text-red-400 border border-red-500/20'}"
        >
            <div class="flex items-center gap-3">
                {#if message.type === 'success'}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M5 13l4 4L19 7" />
                    </svg>
                {:else}
                    <svg class="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                    </svg>
                {/if}
                <span class="font-bold text-sm">{message.text}</span>
            </div>
        </div>
    {/if}

    {#if loading}
        <div class="grid grid-cols-1 md:grid-cols-2 gap-6" aria-busy="true">
            {#each [1, 2, 3, 4] as _}
                <div class="h-48 bg-slate-100 dark:bg-slate-800/50 rounded-3xl animate-pulse border border-slate-200 dark:border-slate-700/50"></div>
            {/each}
        </div>
    {:else}
        {#if tabs}
            {@render tabs()}
        {/if}
        <div class="space-y-6">
            {@render children()}
        </div>
    {/if}
</div>

{#if isDirty && !loading}
    <div class="fixed bottom-0 left-0 right-0 bg-white/95 dark:bg-slate-900/95 backdrop-blur-lg border-t border-slate-200 dark:border-slate-700 shadow-2xl z-50 animate-in slide-in-from-bottom-4">
        <div class="max-w-4xl mx-auto px-4 py-4 flex items-center justify-between gap-4">
            <div class="flex items-center gap-3 text-slate-600 dark:text-slate-400">
                <svg class="w-5 h-5 text-amber-500" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2.5" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                </svg>
                <span class="text-sm font-bold">{$_('common.unsaved_changes')}</span>
            </div>
            <button
                type="button"
                onclick={() => onSave?.()}
                disabled={saving}
                class="px-8 py-3 bg-gradient-to-r from-teal-500 to-emerald-500 hover:from-teal-600 hover:to-emerald-600 text-white font-black text-sm uppercase tracking-widest rounded-2xl shadow-lg shadow-teal-500/30 transition-all disabled:opacity-50"
            >
                {saving ? $_('common.saving') : $_('common.apply_settings')}
            </button>
        </div>
    </div>
{/if}
