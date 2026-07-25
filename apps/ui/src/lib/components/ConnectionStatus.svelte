<script lang="ts">
    import { _ } from 'svelte-i18n';

    let {
        birdnetEnabled = false,
        notificationsActive = false,
        connected = false,
        className = 'gap-4',
        variant = 'compact'
    }: {
        birdnetEnabled?: boolean;
        notificationsActive?: boolean;
        connected?: boolean;
        className?: string;
        variant?: 'compact' | 'sidebar';
    } = $props();
</script>

{#if variant === 'sidebar'}
    <div class="space-y-1" role="status" aria-live="polite">
        <div class="flex min-h-7 items-center gap-2 rounded-lg px-2 text-xs text-slate-600 dark:text-slate-300">
            <span class="relative flex h-2 w-2 flex-shrink-0">
                {#if connected}
                    <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-20"></span>
                {/if}
                <span class="relative inline-flex h-2 w-2 rounded-full {connected ? 'bg-emerald-500 dark:bg-emerald-400' : 'bg-red-500'}"></span>
            </span>
            <span class="min-w-0 flex-1 truncate">{$_('status.live_updates')}</span>
            <span class="flex-shrink-0 text-[0.625rem] font-semibold {connected ? 'text-emerald-700 dark:text-emerald-300' : 'text-red-600 dark:text-red-400'}">
                {connected ? $_('status.online') : $_('status.offline')}
            </span>
        </div>

        <div class="flex min-h-7 items-center gap-2 rounded-lg px-2 text-xs text-slate-600 dark:text-slate-300">
            <span class="inline-flex h-2 w-2 flex-shrink-0 rounded-full {birdnetEnabled ? 'bg-brand-500 dark:bg-brand-400' : 'bg-slate-300 dark:bg-slate-600'}"></span>
            <span class="min-w-0 flex-1 truncate">{$_('status.audio_analysis')}</span>
            <span class="flex-shrink-0 text-[0.625rem] font-semibold {birdnetEnabled ? 'text-brand-700 dark:text-brand-300' : 'text-slate-400 dark:text-slate-500'}">
                {birdnetEnabled ? $_('common.enabled') : $_('common.disabled')}
            </span>
        </div>

        <div class="flex min-h-7 items-center gap-2 rounded-lg px-2 text-xs text-slate-600 dark:text-slate-300">
            <span class="inline-flex h-2 w-2 flex-shrink-0 rounded-full {notificationsActive ? 'bg-indigo-500 dark:bg-indigo-400' : 'bg-slate-300 dark:bg-slate-600'}"></span>
            <span class="min-w-0 flex-1 truncate">{$_('status.notifications')}</span>
            <span class="flex-shrink-0 text-[0.625rem] font-semibold {notificationsActive ? 'text-indigo-700 dark:text-indigo-300' : 'text-slate-400 dark:text-slate-500'}">
                {notificationsActive ? $_('common.enabled') : $_('common.disabled')}
            </span>
        </div>
    </div>
{:else}
    <div class={`flex items-center ${className}`}>
        {#if birdnetEnabled}
            <div class="group relative flex cursor-help items-center justify-center text-brand-500 dark:text-brand-400" title={$_('status.audio_active')}>
                <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-brand-400 opacity-20"></span>
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
            </div>
        {/if}

        {#if notificationsActive}
            <div class="relative flex cursor-help items-center justify-center text-indigo-500 dark:text-indigo-400" title={$_('status.notifications_enabled')}>
                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h6m-6 8 4-4h6a4 4 0 0 0 4-4V7a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v9a4 4 0 0 0 4 4z" /></svg>
            </div>
        {/if}

        <div class="flex cursor-help items-center gap-2" title={connected ? $_('status.system_online') : $_('status.system_offline')}>
            {#if connected}
                <div class="relative flex items-center justify-center text-accent-500 dark:text-accent-400">
                    <span class="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-400 opacity-20"></span>
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
                </div>
            {:else}
                <div class="relative flex items-center justify-center text-red-500">
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                </div>
            {/if}
        </div>
    </div>
{/if}
