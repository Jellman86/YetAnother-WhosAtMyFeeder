<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Snippet } from 'svelte';
    import CameraStatus from './CameraStatus.svelte';
    import NotificationCenter from './NotificationCenter.svelte';

    type Props = {
        title: string;
        subtitle?: string;
        onNavigate?: (path: string) => void;
        actions?: Snippet;
    };

    let { title, subtitle, onNavigate, actions }: Props = $props();

    function goSettings() {
        onNavigate?.('/settings');
    }
</script>

<header class="flex items-center justify-between gap-4 mb-6">
    <div class="min-w-0 flex-1">
        <h1 class="text-2xl sm:text-3xl font-black text-slate-900 dark:text-white tracking-tight truncate">{title}</h1>
        {#if subtitle}
            <p class="text-sm text-slate-500 dark:text-slate-400 font-medium truncate">{subtitle}</p>
        {/if}
    </div>
    <div class="flex items-center gap-1 shrink-0">
        {#if actions}
            {@render actions()}
        {:else}
            <CameraStatus />
            <NotificationCenter
                onNavigate={(path) => onNavigate?.(path)}
                buttonClass="relative p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
            />
            <button
                type="button"
                onclick={goSettings}
                class="p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
                title={$_('nav.settings')}
                aria-label={$_('nav.settings')}
            >
                <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z" />
                    <path stroke-linecap="round" stroke-linejoin="round" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
                </svg>
            </button>
        {/if}
    </div>
</header>
