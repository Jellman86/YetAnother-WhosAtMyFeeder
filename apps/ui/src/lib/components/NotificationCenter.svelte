<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { notificationCenter, type NotificationItem } from '../stores/notification_center.svelte';

    let {
        position = 'top',
        align = 'right',
        placement = 'inside',
        showLabel = false,
        label = '',
        collapsed = false,
        buttonClass = 'relative p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring'
    } = $props<{
        position?: 'top' | 'bottom';
        align?: 'left' | 'right';
        placement?: 'inside' | 'outside';
        showLabel?: boolean;
        label?: string;
        collapsed?: boolean;
        buttonClass?: string;
    }>();

    let open = $state(false);
    let panelRef = $state<HTMLDivElement | null>(null);

    let items = $derived(notificationCenter.items);
    let ongoingItems = $derived(items.filter((item) => item.type === 'process' && !item.read));
    let historyItems = $derived(items.filter((item) => !(item.type === 'process' && !item.read)));
    let unreadCount = $derived(items.filter((item) => !item.read).length);
    const panelPositionClass = $derived(
        position === 'bottom'
            ? 'bottom-full mb-2'
            : 'top-full mt-2'
    );
    const panelAlignClass = $derived(() => {
        if (placement === 'outside') {
            return align === 'left'
                ? 'left-full ml-3'
                : 'right-full mr-3';
        }
        return align === 'left'
            ? 'left-0'
            : 'right-0';
    });

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

    function getProgress(item: NotificationItem) {
        const meta = item.meta ?? {};
        const total = Number(meta.total ?? 0);
        const current = Number(meta.current ?? meta.processed ?? 0);
        if (!Number.isFinite(total) || total <= 0) return null;
        const percent = Math.min(100, Math.max(0, Math.round((current / total) * 100)));
        return { percent, current, total };
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
        class={buttonClass}
        onclick={toggle}
        aria-label={label || $_('notifications.center_title')}
    >
        <svg xmlns="http://www.w3.org/2000/svg" class="h-5 w-5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
            <path stroke-linecap="round" stroke-linejoin="round" d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0a3 3 0 01-6 0m6 0H9" />
        </svg>
        {#if showLabel && !collapsed}
            <span class="text-sm font-medium">{label || $_('notifications.center_title')}</span>
        {/if}
        {#if unreadCount > 0}
            <span class="absolute -top-1 -right-1 min-w-[18px] h-5 px-1 rounded-full bg-rose-500 text-white text-[10px] font-black flex items-center justify-center shadow">
                {unreadCount > 9 ? '9+' : unreadCount}
            </span>
        {/if}
    </button>

    {#if open}
        <div class={`absolute ${panelAlignClass} ${panelPositionClass} w-[320px] max-w-[90vw] rounded-2xl bg-white dark:bg-slate-900 shadow-xl border border-slate-200 dark:border-slate-700/60 overflow-hidden z-50`}>
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
                    {#if ongoingItems.length > 0}
                        <div class="px-4 py-3 border-b border-slate-200/70 dark:border-slate-800/60 bg-gradient-to-b from-emerald-50/70 to-white dark:from-emerald-500/10 dark:to-slate-900/60">
                            <div class="flex items-center justify-between">
                                <div class="text-[10px] font-black uppercase tracking-widest text-emerald-600/80 dark:text-emerald-300/80">{$_('notifications.center_ongoing')}</div>
                                <span class="text-[10px] font-semibold text-slate-400">{ongoingItems.length}</span>
                            </div>
                            <div class="mt-3 space-y-2">
                                {#each ongoingItems as item (item.id)}
                                    {@const progress = getProgress(item)}
                                    <div class="rounded-xl border border-emerald-100/80 dark:border-emerald-900/50 bg-white/80 dark:bg-slate-900/70 px-3 py-2 shadow-sm">
                                        <div class="flex items-center justify-between gap-2">
                                            <div class="flex items-center gap-2">
                                                <span class="text-base">{getIcon(item.type)}</span>
                                                <span class="text-xs font-semibold text-slate-900 dark:text-white">{item.title}</span>
                                            </div>
                                            {#if progress}
                                                <span class="text-[10px] font-black text-emerald-600 dark:text-emerald-300">{progress.percent}%</span>
                                            {/if}
                                        </div>
                                        {#if item.message}
                                            <p class="text-[10px] font-medium text-slate-500 dark:text-slate-300 mt-1">{item.message}</p>
                                        {/if}
                                        {#if progress}
                                            <div class="mt-2 h-2 rounded-full bg-emerald-100 dark:bg-emerald-950/60 overflow-hidden">
                                                <div class="h-full bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 transition-all duration-500" style={`width: ${progress.percent}%`}></div>
                                            </div>
                                            <div class="mt-1 flex items-center justify-between text-[9px] font-semibold text-slate-400">
                                                <span>{progress.current.toLocaleString()} / {progress.total.toLocaleString()}</span>
                                                <span>{$_('notifications.center_ongoing_label')}</span>
                                            </div>
                                        {/if}
                                    </div>
                                {/each}
                            </div>
                        </div>
                    {/if}

                    <div class="px-4 py-2 text-[10px] font-black uppercase tracking-widest text-slate-500">
                        {$_('notifications.center_history')}
                    </div>
                    {#if historyItems.length === 0}
                        <div class="px-4 py-4 text-center text-xs text-slate-500">
                            {$_('notifications.center_history_empty')}
                        </div>
                    {:else}
                        {#each historyItems as item (item.id)}
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
                    {/if}
                </div>
            {/if}
        </div>
    {/if}
</div>
