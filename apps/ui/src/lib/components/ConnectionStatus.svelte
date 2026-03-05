<script lang="ts">
    import { _ } from 'svelte-i18n';

    let {
        birdnetEnabled = false,
        notificationsActive = false,
        connected = false,
        className = 'gap-4'
    }: {
        birdnetEnabled?: boolean;
        notificationsActive?: boolean;
        connected?: boolean;
        className?: string;
    } = $props();
</script>

<div class={`flex items-center ${className}`}>
    {#if birdnetEnabled}
        <div class="relative flex items-center justify-center group cursor-help text-teal-500 dark:text-teal-400" title={$_('status.audio_active')}>
            <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-400 opacity-20"></span>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M15.536 8.464a5 5 0 010 7.072m2.828-9.9a9 9 0 010 12.728M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" /></svg>
        </div>
    {/if}

    {#if notificationsActive}
        <div class="relative flex items-center justify-center text-indigo-500 dark:text-indigo-400 cursor-help" title={$_('status.notifications_enabled')}>
            <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M7 8h10M7 12h6m-6 8 4-4h6a4 4 0 0 0 4-4V7a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v9a4 4 0 0 0 4 4z" /></svg>
        </div>
    {/if}

    <div class="flex items-center gap-2 cursor-help" title={connected ? $_('status.system_online') : $_('status.system_offline')}>
        {#if connected}
            <div class="relative flex items-center justify-center text-emerald-500 dark:text-emerald-400">
                <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-20"></span>
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 12h14M5 12a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v4a2 2 0 01-2 2M5 12a2 2 0 00-2 2v4a2 2 0 002 2h14a2 2 0 002-2v-4a2 2 0 00-2-2m-2-4h.01M17 16h.01" /></svg>
            </div>
        {:else}
            <div class="relative flex items-center justify-center text-red-500">
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
            </div>
        {/if}
    </div>
</div>
