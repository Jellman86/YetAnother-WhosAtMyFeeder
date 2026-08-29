<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { ClassifierStatus } from '../../api';

    let {
        classifierStatus,
        imageExecutionMode,
        activeProviderLabel,
        issueCount,
        modelsAnchorId,
        reportAnchorId,
    }: {
        classifierStatus: ClassifierStatus | null;
        imageExecutionMode: string;
        activeProviderLabel: string;
        issueCount: number;
        modelsAnchorId: string;
        reportAnchorId: string;
    } = $props();

    const loaded = $derived(classifierStatus?.loaded ?? false);
    const modelValue = $derived(classifierStatus?.active_model_id ?? null);
    const labelsCount = $derived(classifierStatus?.labels_count ?? 0);
    const providerVerified = $derived(
        Boolean(
            classifierStatus?.active_provider &&
                (classifierStatus?.host_device_eligibility?.verified_providers ?? []).includes(
                    classifierStatus.active_provider
                )
        )
    );
    const liveWorkers = $derived(classifierStatus?.resolved_live_workers ?? 1);
    const backgroundWorkers = $derived(classifierStatus?.resolved_background_workers ?? 1);
    const ramPerCopy = $derived(classifierStatus?.active_model_estimated_ram_mb ?? null);

    function jumpTo(anchorId: string) {
        document.getElementById(anchorId)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
    }
</script>

<!-- The state you previously dug three disclosures for, always on top: healthy
     is four calm facts, and only trouble grows words. -->
<div
    role="status"
    class="relative grid grid-cols-2 gap-4 overflow-hidden rounded-2xl border border-brand-500/25 bg-white/60 p-4 dark:bg-slate-900/40 lg:grid-cols-4"
>
    <span class="card-aurora" aria-hidden="true"></span>
    <button
        type="button"
        onclick={() => jumpTo(modelsAnchorId)}
        class="group relative flex min-h-11 cursor-pointer flex-col gap-0.5 rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
    >
        <span class="text-xs font-black uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.detection.band_model')}</span>
        <span class="break-all text-sm font-bold text-slate-900 group-hover:text-brand-700 dark:text-white dark:group-hover:text-brand-300">
            {modelValue ?? $_('settings.detection.band_no_model')}
        </span>
        <!-- Subprocess workers load the model on first use, so "not loaded yet"
             is a normal idle state, never a warning. -->
        <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
            {loaded || labelsCount > 0
                ? $_('settings.detection.band_species_count', { values: { count: labelsCount } })
                : $_('settings.detection.band_not_loaded')}
        </span>
    </button>

    <div class="relative flex flex-col gap-0.5">
        <span class="text-xs font-black uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.detection.band_runtime')}</span>
        <span class="text-sm font-bold text-slate-900 dark:text-white">{activeProviderLabel}</span>
        {#if classifierStatus?.fallback_reason}
            <span class="text-xs font-semibold text-amber-700 dark:text-amber-300">{$_('settings.detection.band_fallback_active')}</span>
        {:else if providerVerified}
            <span class="inline-flex items-center gap-1 text-xs font-semibold text-accent-700 dark:text-accent-300">
                {$_('settings.detection.band_verified')}
                <svg class="h-3 w-3" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="m3 8.5 3.5 3.5L13 4.5" /></svg>
            </span>
        {:else}
            <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.detection.band_unverified')}</span>
        {/if}
    </div>

    <div class="relative flex flex-col gap-0.5">
        <span class="text-xs font-black uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.detection.band_workers')}</span>
        {#if imageExecutionMode === 'in_process'}
            <span class="text-sm font-bold text-slate-900 dark:text-white">{$_('settings.detection.band_in_process')}</span>
            <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">{$_('settings.detection.band_shared_runtime')}</span>
        {:else}
            <span class="text-sm font-bold text-slate-900 dark:text-white">
                {$_('settings.detection.band_worker_split', { values: { live: liveWorkers, background: backgroundWorkers } })}
            </span>
            <span class="text-xs font-semibold text-slate-500 dark:text-slate-400">
                {#if ramPerCopy}
                    {$_('settings.detection.band_ram_per_copy', { values: { mb: ramPerCopy } })}
                {:else}
                    {$_('settings.detection.band_own_copy_each')}
                {/if}
            </span>
        {/if}
    </div>

    <button
        type="button"
        onclick={() => jumpTo(reportAnchorId)}
        class="group relative flex min-h-11 cursor-pointer flex-col gap-0.5 rounded-xl text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500"
    >
        <span class="text-xs font-black uppercase tracking-[0.14em] text-slate-500 dark:text-slate-400">{$_('settings.detection.band_health')}</span>
        {#if issueCount > 0}
            <span class="text-sm font-bold text-amber-700 dark:text-amber-300">
                {$_('settings.detection.band_needs_attention', { values: { count: issueCount } })}
            </span>
        {:else}
            <span class="text-sm font-bold text-accent-700 dark:text-accent-300">{$_('settings.detection.band_all_good')}</span>
        {/if}
        <span class="text-xs font-semibold text-brand-700 underline-offset-2 group-hover:underline dark:text-brand-300">
            {$_('settings.detection.band_full_report')}
        </span>
    </button>
</div>
