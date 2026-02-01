<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { notificationCenter, type NotificationItem } from '../stores/notification_center.svelte';

    let items = $derived(notificationCenter.items);
    let ongoingItems = $derived(items.filter((item) => item.type === 'process' && !item.read));
    let historyItems = $derived(items.filter((item) => !(item.type === 'process' && !item.read)));

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
</script>

<div class="space-y-6">
    <div class="flex items-center justify-between">
        <div>
            <h2 class="text-2xl font-black text-slate-900 dark:text-white tracking-tight">{$_('notifications.page_title')}</h2>
            <p class="text-xs text-slate-500">{$_('notifications.page_subtitle')}</p>
        </div>
        <div class="flex items-center gap-2 text-[11px] font-semibold text-slate-500">
            <button type="button" class="px-3 py-2 rounded-xl border border-slate-200/70 dark:border-slate-700/60 hover:bg-slate-100 dark:hover:bg-slate-800" onclick={() => notificationCenter.markAllRead()}>
                {$_('notifications.center_mark_all')}
            </button>
            <button type="button" class="px-3 py-2 rounded-xl border border-slate-200/70 dark:border-slate-700/60 hover:bg-slate-100 dark:hover:bg-slate-800" onclick={() => notificationCenter.clear()}>
                {$_('notifications.center_clear')}
            </button>
        </div>
    </div>

    {#if items.length === 0}
        <div class="card-base p-8 text-center text-sm text-slate-500">
            {$_('notifications.page_empty')}
        </div>
    {:else}
        <div class="grid grid-cols-1 gap-6">
            <section class="card-base p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-xs font-black uppercase tracking-widest text-emerald-600/80 dark:text-emerald-300/80">{$_('notifications.page_ongoing')}</h3>
                    <span class="text-[10px] font-semibold text-slate-400">{ongoingItems.length}</span>
                </div>
                {#if ongoingItems.length === 0}
                    <p class="text-xs text-slate-500">{$_('notifications.center_history_empty')}</p>
                {:else}
                    <div class="space-y-3">
                        {#each ongoingItems as item (item.id)}
                            {@const progress = getProgress(item)}
                            <div class="rounded-2xl border border-emerald-100/80 dark:border-emerald-900/50 bg-white/80 dark:bg-slate-900/70 px-4 py-3 shadow-sm">
                                <div class="flex items-center justify-between gap-2">
                                    <div class="flex items-center gap-2">
                                        <span class="text-lg">{getIcon(item.type)}</span>
                                        <span class="text-sm font-semibold text-slate-900 dark:text-white">{item.title}</span>
                                    </div>
                                    {#if progress}
                                        <span class="text-[10px] font-black text-emerald-600 dark:text-emerald-300">{progress.percent}%</span>
                                    {/if}
                                </div>
                                {#if item.message}
                                    <p class="text-xs text-slate-500 dark:text-slate-300 mt-1">{item.message}</p>
                                {/if}
                                {#if progress}
                                    <div class="mt-3 h-2 rounded-full bg-emerald-100 dark:bg-emerald-950/60 overflow-hidden">
                                        <div class="h-full bg-gradient-to-r from-emerald-500 via-teal-500 to-sky-500 transition-all duration-500" style={`width: ${progress.percent}%`}></div>
                                    </div>
                                    <div class="mt-1 flex items-center justify-between text-[10px] font-semibold text-slate-400">
                                        <span>{progress.current.toLocaleString()} / {progress.total.toLocaleString()}</span>
                                        <span>{$_('notifications.center_ongoing_label')}</span>
                                    </div>
                                {/if}
                            </div>
                        {/each}
                    </div>
                {/if}
            </section>

            <section class="card-base p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-xs font-black uppercase tracking-widest text-slate-500">{$_('notifications.page_history')}</h3>
                    <span class="text-[10px] font-semibold text-slate-400">{historyItems.length}</span>
                </div>
                {#if historyItems.length === 0}
                    <p class="text-xs text-slate-500">{$_('notifications.center_history_empty')}</p>
                {:else}
                    <div class="divide-y divide-slate-100 dark:divide-slate-800/60">
                        {#each historyItems as item (item.id)}
                            <button
                                type="button"
                                class="w-full text-left py-3 hover:bg-slate-50 dark:hover:bg-slate-800/40 transition px-2 rounded-xl"
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
            </section>
        </div>
    {/if}
</div>
