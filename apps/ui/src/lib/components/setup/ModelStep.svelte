<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchClassifierStatus, type ClassifierStatus } from '../../api/classifier';
    import {
        startModelEvalRun,
        listModelEvalRuns,
        getModelEvalRun,
        type ModelEvalModelSummary
    } from '../../api/model_eval';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let status = $state<ClassifierStatus | null>(null);
    let validating = $state(false);
    let progress = $state<{ done: number; total: number; label: string; phase: string } | null>(null);
    let results = $state<ModelEvalModelSummary[] | null>(null);
    let errorMsg = $state('');
    let runId = '';
    let poller: ReturnType<typeof setInterval> | null = null;

    let accelerators = $derived([
        { id: 'intel_npu', label: 'Intel NPU', available: status?.intel_npu_available },
        { id: 'intel_gpu', label: 'Intel iGPU', available: status?.intel_gpu_available },
        { id: 'cuda', label: 'NVIDIA CUDA', available: status?.cuda_available },
        { id: 'cpu', label: 'CPU', available: status?.intel_cpu_available ?? true }
    ]);
    let verified = $derived(status?.host_device_eligibility?.verified_providers ?? []);
    let activeModel = $derived(setupWizardStore.detailFor('model'));
    let progressPct = $derived(progress && progress.total > 0 ? Math.round((progress.done / progress.total) * 100) : 0);

    onMount(async () => {
        try {
            status = await fetchClassifierStatus();
        } catch {
            status = null;
        }
    });

    onDestroy(() => {
        if (poller) clearInterval(poller);
    });

    function stopPolling() {
        if (poller) clearInterval(poller);
        poller = null;
    }

    async function poll() {
        try {
            const list = await listModelEvalRuns();
            if (list.active && list.active.run_id === runId) {
                progress = { ...list.active.progress, phase: list.active.phase };
                return;
            }
            // No active run for our id -> it finished; pull the results once.
            stopPolling();
            const summary = await getModelEvalRun(runId);
            results = summary.models ?? [];
            validating = false;
            progress = null;
            await fetchClassifierStatus().then((s) => (status = s)).catch(() => {});
        } catch {
            // Transient; keep polling until it resolves or the user leaves the step.
        }
    }

    async function runValidation() {
        errorMsg = '';
        results = null;
        validating = true;
        progress = { done: 0, total: 0, label: $_('setup.model.starting', { default: 'Starting…' }), phase: 'starting' };
        try {
            const { run_id } = await startModelEvalRun({ sweep_devices: true, compat_only: true });
            runId = run_id;
            poller = setInterval(poll, 2000);
        } catch (err) {
            validating = false;
            progress = null;
            errorMsg = err instanceof Error ? err.message : $_('setup.model.sweep_error', { default: 'Could not start validation.' });
        }
    }

    function rowOk(m: ModelEvalModelSummary): boolean {
        return m.ready && !m.warnings.some((w) => w.severity === 'critical');
    }
</script>

<WizardStepLayout
    title={$_('setup.model.title', { default: 'Classifier model & hardware' })}
    description={$_('setup.model.description', {
        default: 'YA-WAMF ships with a working classifier. Validate it on your hardware so it runs on your accelerator — with a clean CPU fallback if it does not.'
    })}
>
    <div class="rounded-xl border border-slate-200 p-3 dark:border-slate-700">
        <p class="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">{$_('setup.model.active', { default: 'Active model' })}</p>
        <p class="text-sm font-medium text-slate-800 dark:text-slate-100">{activeModel ?? $_('setup.model.bundled', { default: 'Bundled default' })}</p>
    </div>

    <div>
        <p class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.detected', { default: 'Detected accelerators' })}</p>
        <div class="mt-1.5 flex flex-wrap gap-2">
            {#each accelerators as acc}
                <span class="inline-flex items-center gap-1 rounded-full px-2.5 py-1 text-xs font-semibold {acc.available ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}">
                    <span aria-hidden="true">{acc.available ? '✓' : '—'}</span> {acc.label}
                </span>
            {/each}
        </div>
        {#if verified.length}
            <p class="mt-2 text-xs text-emerald-700 dark:text-emerald-300">{$_('setup.model.verified', { values: { list: verified.join(', ') }, default: `Validated providers: ${verified.join(', ')}` })}</p>
        {/if}
    </div>

    {#if validating && progress}
        <div class="space-y-2 rounded-xl border border-teal-200 bg-teal-50/50 p-3 dark:border-teal-900/40 dark:bg-teal-950/20">
            <div class="flex items-center justify-between text-sm">
                <span class="font-medium text-teal-800 dark:text-teal-200">{progress.label}</span>
                {#if progress.total > 0}<span class="text-xs text-teal-600 dark:text-teal-400">{progress.done}/{progress.total}</span>{/if}
            </div>
            <div class="h-2 w-full overflow-hidden rounded-full bg-teal-100 dark:bg-teal-900/40">
                <div class="h-full rounded-full bg-teal-500 transition-all duration-500" style="width: {progress.total > 0 ? progressPct : 15}%"></div>
            </div>
            <p class="text-xs capitalize text-teal-600 dark:text-teal-400">{progress.phase.replace(/_/g, ' ')}</p>
        </div>
    {:else}
        <button type="button" class="btn btn-secondary px-5 py-2.5" onclick={runValidation}>
            {results ? $_('setup.model.revalidate', { default: 'Re-run validation' }) : $_('setup.model.validate', { default: 'Validate on my hardware' })}
        </button>
    {/if}

    {#if errorMsg}
        <div role="status" class="rounded-md bg-amber-50 p-2 text-sm text-amber-800 dark:bg-amber-900/20 dark:text-amber-200">{errorMsg}</div>
    {/if}

    {#if results}
        {#if results.length === 0}
            <p class="text-sm text-slate-500 dark:text-slate-400">{$_('setup.model.no_results', { default: 'No installed models were evaluated.' })}</p>
        {:else}
            <ul class="divide-y divide-slate-200 overflow-hidden rounded-xl border border-slate-200 dark:divide-slate-700 dark:border-slate-700">
                {#each results as m}
                    <li class="flex items-center justify-between gap-3 p-2.5">
                        <div class="min-w-0">
                            <p class="truncate text-sm font-medium text-slate-800 dark:text-slate-100">{m.model_id}</p>
                            <p class="text-xs text-slate-500 dark:text-slate-400">
                                {m.device ?? m.active_provider ?? 'cpu'}{#if m.mean_latency_ms} · {m.mean_latency_ms.toFixed(0)} ms{/if}
                            </p>
                        </div>
                        <span class="shrink-0 rounded-full px-2 py-0.5 text-xs font-semibold {rowOk(m) ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200' : 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-200'}">
                            {rowOk(m) ? $_('setup.model.row_ok', { default: 'Runs' }) : $_('setup.model.row_warn', { default: 'Check' })}
                        </span>
                    </li>
                {/each}
            </ul>
            <p class="text-xs text-slate-500 dark:text-slate-400">{$_('setup.model.results_hint', { default: 'Full per-device compile, latency, and accuracy detail is in Diagnostics → Model evaluation.' })}</p>
        {/if}
    {/if}
</WizardStepLayout>
