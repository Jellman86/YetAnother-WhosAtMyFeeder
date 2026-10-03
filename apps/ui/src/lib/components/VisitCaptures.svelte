<script lang="ts">
    import { onDestroy, untrack } from 'svelte';
    import { _ } from 'svelte-i18n';
    import DetectionRow from './DetectionRow.svelte';
    import { fetchVisitCaptures, type DetectionVisit, type VisitOptions } from '../api/visits';
    import { authStore } from '../stores/auth.svelte';
    import { detectionsStore } from '../stores/detections.svelte';
    import type { Detection } from '../api';

    interface Props {
        visit: DetectionVisit;
        window?: VisitOptions;
        onselect?: (detection: Detection) => void;
        onplay?: (detection: Detection) => void;
    }
    let { visit, window = {}, onselect, onplay }: Props = $props();
    let open = $state(false);
    let result = $state<{ key: string; captures: Detection[]; total: number } | null>(null);
    let pendingKey = $state('');
    let failedKey = $state('');
    let controller: AbortController | null = null;
    const membershipKey = $derived(JSON.stringify([
        visit.visit_id, visit.capture_count, visit.end_time, visit.representative.display_name,
        window.startDate, window.endDate, window.startTime, window.endTime, window.onlyHidden,
        authStore.hasOwnerAccess, detectionsStore.publicHistoryVersion
    ]));
    const captures = $derived(result?.key === membershipKey ? result.captures : []);
    const total = $derived(result?.key === membershipKey ? result.total : 0);
    const loading = $derived(pendingKey === membershipKey);
    const error = $derived(failedKey === membershipKey);
    const span = $derived.by(() => {
        const options: Intl.DateTimeFormatOptions = { hour: '2-digit', minute: '2-digit' };
        const start = new Date(visit.start_time).toLocaleTimeString(undefined, options);
        const end = new Date(visit.end_time).toLocaleTimeString(undefined, options);
        return start === end ? start : `${start}–${end}`;
    });
    const peak = $derived(visit.peak_capture?.bird_summary?.counted ?? null);

    async function load(reset = false): Promise<void> {
        const key = membershipKey;
        if (pendingKey === key) return;
        controller?.abort();
        const current = new AbortController();
        controller = current;
        pendingKey = key;
        failedKey = '';
        const previous = !reset && result?.key === key ? result.captures : [];
        try {
            const response = await fetchVisitCaptures(visit.visit_id, {
                ...window, limit: 20, offset: previous.length, signal: current.signal
            });
            if (current.signal.aborted || key !== membershipKey) return;
            result = { key, captures: [...previous, ...response.captures], total: response.total };
        } catch (failure) {
            if (!current.signal.aborted && key === membershipKey && !(failure instanceof Error && failure.name === 'AbortError')) failedKey = key;
        } finally {
            if (controller === current) pendingKey = '';
        }
    }
    $effect(() => {
        const key = membershipKey;
        if (!open) return;
        untrack(() => { if (result?.key !== key) void load(true); });
    });
    onDestroy(() => controller?.abort());
</script>

<details class="group border-t border-slate-200 dark:border-slate-800" data-visit-captures={visit.visit_id}
    ontoggle={(event) => { open = event.currentTarget.open; if (open) void load(true); }}>
    <summary class="min-h-11 cursor-pointer px-4 py-3 text-sm text-slate-600 hover:bg-slate-50 focus-visible:ring-2 focus-visible:ring-primary-500 dark:text-slate-300 dark:hover:bg-slate-800/60">
        <svg class="mr-2 inline h-4 w-4 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" aria-hidden="true"><path d="m5 7 5 5 5-5" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
        <span class="font-medium">{$_('visits.captures', { values: { count: visit.capture_count }, default: '{count} captures' })}</span>
        <span class="ml-2 text-xs text-slate-500 dark:text-slate-400">{span}</span>
        {#if peak !== null && peak >= 2}
            <span class="mt-1 block text-xs">{$_('visits.peak_birds', { values: { count: peak }, default: '{count} birds in one capture' })}</span>
        {/if}
    </summary>
    <div aria-busy={loading} class="border-t border-slate-200 dark:border-slate-800">
        <p class="px-4 py-2 text-xs text-slate-500 dark:text-slate-400">{$_('visits.capture_actions', { default: 'Open a capture to review its identification or play its clip.' })}</p>
        {#each captures as capture (capture.frigate_event)}
            <DetectionRow detection={capture} onclick={() => onselect?.(capture)} onPlay={onplay ? () => onplay?.(capture) : undefined} />
        {/each}
        {#if loading}<p role="status" class="px-4 py-3 text-sm text-slate-500">{$_('common.loading')}</p>{/if}
        {#if error}
            <div class="flex flex-wrap items-center gap-3 p-4" role="alert">
                <p class="text-sm text-slate-600 dark:text-slate-300">{$_('visits.load_failed', { default: 'Could not load the captures. Try again.' })}</p>
                <button class="btn btn-secondary min-h-11" onclick={() => void load()}>{$_('common.retry', { default: 'Retry' })}</button>
            </div>
        {:else if captures.length < total && !loading}
            <button class="btn btn-secondary m-4 min-h-11" onclick={() => void load()}>{$_('visits.load_more', { default: 'Load more captures' })}</button>
        {/if}
    </div>
</details>
