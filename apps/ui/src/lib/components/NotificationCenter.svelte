<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { notificationCenter } from '../stores/notification_center.svelte';

    let {
        showLabel = false,
        label = '',
        collapsed = false,
        buttonClass = 'relative p-2.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 dark:text-slate-400 transition-all duration-200 focus-ring',
        onNavigate,
    } = $props<{
        showLabel?: boolean;
        label?: string;
        collapsed?: boolean;
        buttonClass?: string;
        onNavigate?: (path: string) => void;
    }>();

    let items = $derived(notificationCenter.items);
    let unreadCount = $derived(items.filter((item) => !item.read).length);

    function handleExpand() {
        if (onNavigate) {
            onNavigate('/notifications');
        } else {
            window.location.assign('/notifications');
        }
    }
</script>

<div class="relative">
    <button
        type="button"
        class={buttonClass}
        onclick={handleExpand}
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
</div>
