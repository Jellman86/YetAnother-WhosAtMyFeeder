<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchClassifierStatus, type ClassifierStatus } from '../../api/classifier';
    import { startModelEvalRun } from '../../api/model_eval';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let status = $state<ClassifierStatus | null>(null);
    let sweepState = $state<'idle' | 'starting' | 'started' | 'error'>('idle');
    let sweepMessage = $state('');

    let accelerators = $derived([
        { id: 'intel_npu', label: 'Intel NPU', available: status?.intel_npu_available },
        { id: 'intel_gpu', label: 'Intel iGPU', available: status?.intel_gpu_available },
        { id: 'cuda', label: 'NVIDIA CUDA', available: status?.cuda_available },
        { id: 'cpu', label: 'CPU', available: status?.intel_cpu_available ?? true }
    ]);
    let verified = $derived(status?.host_device_eligibility?.verified_providers ?? []);
    let activeModel = $derived(setupWizardStore.detailFor('model'));

    onMount(async () => {
        try {
            status = await fetchClassifierStatus();
        } catch {
            status = null;
        }
    });

    async function runValidation() {
        sweepState = 'starting';
        sweepMessage = '';
        try {
            await startModelEvalRun({ sweep_devices: true, compat_only: true });
            sweepState = 'started';
            sweepMessage = $_('setup.model.sweep_started', { default: 'Hardware validation is running. See Diagnostics → Model evaluation for per-device compile and latency results.' });
        } catch (err) {
            sweepState = 'error';
            sweepMessage = err instanceof Error ? err.message : $_('setup.model.sweep_error', { default: 'Could not start validation.' });
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.model.title', { default: 'Classifier model & hardware' })}
    description={$_('setup.model.description', {
        default: 'YA-WAMF ships with a working classifier. Validate it on your hardware so it runs on your accelerator — with a clean CPU fallback if it does not.'
    })}
>
    <div>
        <p class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.active', { default: 'Active model' })}</p>
        <p class="text-sm text-slate-600 dark:text-slate-400">{activeModel ?? $_('setup.model.bundled', { default: 'Bundled default' })}</p>
    </div>

    <div>
        <p class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('setup.model.detected', { default: 'Detected accelerators' })}</p>
        <div class="mt-1 flex flex-wrap gap-2">
            {#each accelerators as acc}
                <span class="rounded-full px-2 py-0.5 text-xs font-semibold {acc.available ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-200' : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'}">
                    {acc.available ? '✓' : '—'} {acc.label}
                </span>
            {/each}
        </div>
        {#if verified.length}
            <p class="mt-2 text-xs text-emerald-700 dark:text-emerald-300">{$_('setup.model.verified', { values: { list: verified.join(', ') }, default: `Validated providers: ${verified.join(', ')}` })}</p>
        {/if}
    </div>

    <button type="button" class="btn btn-secondary" disabled={sweepState === 'starting'} onclick={runValidation}>
        {$_('setup.model.validate', { default: 'Run hardware validation' })}
    </button>
    {#if sweepMessage}
        <div role="status" class="rounded-md p-2 text-sm {sweepState === 'error' ? 'bg-amber-50 text-amber-800 dark:bg-amber-900/20 dark:text-amber-200' : 'bg-teal-50 text-teal-800 dark:bg-teal-900/20 dark:text-teal-200'}">{sweepMessage}</div>
    {/if}
</WizardStepLayout>
