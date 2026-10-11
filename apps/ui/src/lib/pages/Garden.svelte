<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchGarden, reviewGarden, type GardenCapture } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';

    let { onNavigate }: { onNavigate: (path: string) => void } = $props();
    let status = $state<GardenCapture['status']>('pending');
    let items = $state.raw<GardenCapture[]>([]);
    let total = $state(0);
    let offset = $state(0);
    let loading = $state(true);
    let saving = $state<string | null>(null);
    let error = $state<string | null>(null);
    let loadedImages = $state<Record<string, boolean>>({});
    let failedImages = $state<Record<string, boolean>>({});
    let controller: AbortController | null = null;
    let generation = 0;
    let destroyed = false;
    let unregisterRefresh: (() => void) | undefined;
    const views = $derived([
        { id: 'pending' as const, name: $_('garden.pending', { default: 'Needs review' }) },
        { id: 'confirmed' as const, name: $_('garden.confirmed', { default: 'Confirmed animals' }) },
        { id: 'dismissed' as const, name: $_('garden.dismissed', { default: 'Dismissed' }) }
    ]);

    async function load(): Promise<void> {
        const request = ++generation;
        controller?.abort();
        controller = new AbortController();
        loading = true;
        error = null;
        items = [];
        loadedImages = {};
        failedImages = {};
        try {
            const result = await fetchGarden(status, offset, controller.signal);
            if (destroyed || request !== generation) return;
            items = result.items;
            total = result.total;
            if (offset > 0 && items.length === 0) {
                offset = Math.max(0, offset - 8);
                await load();
            }
        } catch (failure) {
            if (destroyed || request !== generation || controller.signal.aborted) return;
            error = failure instanceof Error ? failure.message : $_('garden.load_error', { default: 'Could not load garden captures. Refresh to try again.' });
        } finally {
            if (!destroyed && request === generation) loading = false;
        }
    }

    async function selectView(next: GardenCapture['status']): Promise<void> {
        status = next;
        offset = 0;
        await load();
    }

    async function review(item: GardenCapture, action: 'confirm' | 'dismiss' | 'restore'): Promise<void> {
        if (saving) return;
        saving = item.id;
        error = null;
        try {
            await reviewGarden(item.id, action);
            if (!destroyed) await load();
        } catch (failure) {
            if (!destroyed) error = failure instanceof Error ? failure.message : $_('garden.save_error', { default: 'Could not save your review. Try again.' });
        } finally {
            if (!destroyed) saving = null;
        }
    }

    onMount(() => {
        unregisterRefresh = pageRefreshAction.register(load);
        void load();
    });
    onDestroy(() => {
        destroyed = true;
        generation += 1;
        controller?.abort();
        unregisterRefresh?.();
    });
</script>

<div class="space-y-5" data-garden-history>
    <div class="card-base p-4 space-y-2">
        <p class="eyebrow">{$_('garden.review_only', { default: 'Owner review prototype' })}</p>
        <p class="text-sm text-slate-600 dark:text-slate-400">{$_('garden.review_help', { default: 'Confirm that an animal is present, or dismiss a false detection. Frigate labels are suggestions; species identification is not enabled.' })}</p>
        <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.retention_help', { default: 'Garden visits stay separate from bird totals and exports. Photos remain in Frigate and expire with its retention settings.' })}</p>
    </div>
    <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex flex-wrap gap-2" role="group" aria-label={$_('garden.views', { default: 'Garden review views' })}>
            {#each views as view}
                <button class="tab-button min-h-11 {status === view.id ? 'tab-button-active' : 'tab-button-inactive'}" aria-pressed={status === view.id} disabled={saving !== null} onclick={() => selectView(view.id)}>{view.name}</button>
            {/each}
        </div>
        <button class="btn btn-secondary min-h-11 px-4 py-2" disabled={loading || saving !== null} onclick={load}>{$_('garden.refresh', { default: 'Refresh' })}</button>
    </div>
    {#if error}
        <div class="rounded-xl border border-line bg-surface-raised p-4 text-sm" role="alert">{error}</div>
    {/if}
    <div aria-live="polite" aria-busy={loading}>
        {#if loading}
            <p class="p-6 text-sm text-slate-600 dark:text-slate-400" role="status">{$_('garden.loading', { default: 'Loading garden captures…' })}</p>
        {:else if !error && items.length === 0}
            <div class="card-base space-y-3 p-6">
                <h2 class="font-semibold">{$_('garden.empty', { default: 'No captures in this view' })}</h2>
                <p class="text-sm text-slate-600 dark:text-slate-400">{$_('garden.empty_help', { default: 'Enable Garden animals for a camera in Settings. Completed animal events will appear here for review; birds keep their existing Feeder or Nest role.' })}</p>
                <button class="btn btn-secondary min-h-11 px-4 py-2" onclick={() => onNavigate('/settings/connection')}>{$_('garden.camera_settings', { default: 'Camera settings' })}</button>
            </div>
        {:else}
            <div class="space-y-4">
                {#each items as item (item.id)}
                    <article class="card-base overflow-hidden md:grid md:grid-cols-3" aria-label={item.camera}>
                        <div class="relative aspect-video min-w-0 bg-surface-raised md:col-span-2">
                            {#if item.snapshot_url && !failedImages[item.id]}
                                <img class="absolute inset-0 h-full w-full object-contain" src={withAuthParams(item.snapshot_url)}
                                    alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: item.camera } })}
                                    loading="lazy" onload={() => loadedImages = { ...loadedImages, [item.id]: true }}
                                    onerror={() => failedImages = { ...failedImages, [item.id]: true }} />
                            {:else}
                                <p class="absolute inset-0 flex items-center justify-center p-4 text-center text-sm text-slate-600 dark:text-slate-400">{$_('garden.snapshot_unavailable', { default: 'Snapshot unavailable' })}</p>
                            {/if}
                        </div>
                        <div class="min-w-0 space-y-4 p-4">
                            <div class="space-y-1">
                                <h2 class="break-words font-semibold">{item.camera}</h2>
                                <time class="block text-xs text-slate-600 dark:text-slate-400" datetime={item.observed_at}>{new Date(item.observed_at).toLocaleString()}</time>
                                <p class="break-words text-sm">{$_('garden.frigate_suggested', { default: 'Frigate suggested: {label}', values: { label: item.frigate_label } })}</p>
                                <p class="text-xs text-slate-600 dark:text-slate-400">{views.find(view => view.id === item.status)?.name}</p>
                            </div>
                            <div class="flex flex-col gap-2">
                                {#if item.status === 'pending'}
                                    <button class="btn btn-primary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null || !loadedImages[item.id]} onclick={() => review(item, 'confirm')}>{$_('garden.confirm', { default: 'Confirm animal present' })}</button>
                                {/if}
                                {#if item.status !== 'dismissed'}
                                    <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => review(item, 'dismiss')}>{$_('garden.dismiss', { default: 'Dismiss capture' })}</button>
                                {:else}
                                    <button class="btn btn-secondary min-h-11 px-4 py-2 whitespace-normal" disabled={saving !== null} onclick={() => review(item, 'restore')}>{$_('garden.restore', { default: 'Return to review' })}</button>
                                {/if}
                            </div>
                        </div>
                    </article>
                {/each}
            </div>
        {/if}
    </div>
    {#if !loading && !error && total > 0}
        <div class="flex flex-wrap items-center justify-between gap-3">
            <button class="btn btn-secondary min-h-11 px-4 py-2" disabled={offset === 0 || saving !== null} onclick={() => { offset = Math.max(0, offset - 8); void load(); }}>{$_('garden.previous', { default: 'Previous' })}</button>
            <p class="text-xs text-slate-600 dark:text-slate-400">{$_('garden.page_count', { default: '{start}–{end} of {total}', values: { start: offset + 1, end: Math.min(offset + 8, total), total } })}</p>
            <button class="btn btn-secondary min-h-11 px-4 py-2" disabled={offset + 8 >= total || saving !== null} onclick={() => { offset += 8; void load(); }}>{$_('garden.next', { default: 'Next' })}</button>
        </div>
    {/if}
</div>
