<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { notificationCenter, type NotificationItem } from '../stores/notification_center.svelte';

    let open = $state(false);
    let panelRef = $state<HTMLDivElement | null>(null);

    let items = $derived(notificationCenter.items);
    let unreadCount = $derived(items.filter((item) => !item.read).length);

    function toggle() {
        open = !open;
    }

    function close() {
        open = false;
    }

    function formatTime(ts: number) {
        return new Date(ts).toLocaleString();
    }

    function getIcon(type: NotificationItem['type']) {
        if (type === 'detection') return '🐦';
        if (type === 'update') return '✅';
        if (type === 'process') return '⏳';
        return '🔔';
    }

    onMount(() => {
        const handler = (event: MouseEvent) => {
            if (!open) return;
            if (!panelRef || panelRef.contains(event.target as Node)) return;
            close();
        };
        document.addEventListener('click', handler);
        return () => document.removeEventListener('click', handler);
    });
</script>

<div class="relative" bind:this={panelRef}>
    <button
        type="button"
        class="relative p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring"
        onclick={toggle}
        aria-label={$_('notifications.center_title')}
    >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 01-6 0m6 0H9" />
        </svg>
        {#if unreadCount > 0}
            <span class="absolute -top-1 -right-1 min-w-[18px] h-5 px-1 rounded-full bg-rose-500 text-white text-[10px] font-black flex items-center justify-center shadow">
                {unreadCount > 9 ? '9+' : unreadCount}
            </span>
        {/if}
    </button>

    {#if open}
        <div class="absolute right-0 mt-2 w-[320px] max-w-[90vw] rounded-2xl bg-white dark:bg-slate-900 shadow-xl border border-slate-200 dark:border-slate-700/60 overflow-hidden z-50">
            <div class="flex items-center justify-between px-4 py-3 border-b border-slate-200 dark:border-slate-700/60">
                <div class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('notifications.center_title')}</div>
                <div class="flex items-center gap-2 text-[10px] font-semibold text-slate-400">
                    <button type="button" class="hover:text-slate-600 dark:hover:text-slate-200" onclick={() => notificationCenter.markAllRead()}>
                        {$_('notifications.center_mark_all')}
                    </button>
                    <span>•</span>
                    <button type="button" class="hover:text-slate-600 dark:hover:text-slate-200" onclick={() => notificationCenter.clear()}>
                        {$_('notifications.center_clear')}
                    </button>
                </div>
            </div>

            {#if items.length === 0}
                <div class="px-4 py-6 text-center text-sm text-slate-500">
                    {$_('notifications.center_empty')}
                </div>
            {:else}
                <div class="max-h-[360px] overflow-y-auto">
                    {#each items as item (item.id)}
                        <button
                            type="button"
                            class="w-full text-left px-4 py-3 border-b border-slate-100 dark:border-slate-800/60 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition"
                            onclick={() => notificationCenter.markRead(item.id)}
                        >
                            <div class="flex items-start gap-3">
                                <div class="text-lg">{getIcon(item.type)}</div>
                                <div class="flex-1">
                                    <div class="flex items-center justify-between gap-2">
                                        <p class="text-sm font-semibold text-slate-900 dark:text-white">
                                            {item.title}
                                        </p>
                                        <span class="text-[10px] text-slate-400">{formatTime(item.timestamp)}</span>
                                    </div>
                                    {#if item.message}
                                        <p class="text-xs text-slate-500 dark:text-slate-400 mt-1">{item.message}</p>
                                    {/if}
                                </div>
                                {#if !item.read}
                                    <span class="mt-1 w-2 h-2 rounded-full bg-rose-500"></span>
                                {/if}
                            </div>
                        </button>
                    {/each}
                </div>
            {/if}
        </div>
    {/if}
</div>
