<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { components } from '../api/generated/openapi';

    let { execution }: { execution: Pick<components['schemas']['InferenceExecution'], 'devices' | 'checked_at' | 'fallback_reason'> | null | undefined } = $props();
    const device = $derived(execution?.devices?.map(value => ({ CPUExecutionProvider: 'CPU', CUDAExecutionProvider: 'NVIDIA GPU' })[value as 'CPUExecutionProvider' | 'CUDAExecutionProvider'] ?? value).join(', ') ?? '');
</script>

<div class="space-y-1 text-xs text-slate-600 dark:text-slate-400" data-model-execution>
    {#if execution}
        <p>{$_('model_execution.completed', { default: 'Last completed run: {device} · {time}', values: { device, time: new Date(execution.checked_at).toLocaleString() } })}</p>
        {#if execution.fallback_reason}
            <p>{$_('model_execution.fallback', { default: 'CPU fallback: the requested accelerator did not complete its current check or inference successfully.' })}</p>
        {/if}
    {:else}
        <p>{$_('model_execution.unreported', { default: 'No completed run has reported its device yet. A recommendation is not an execution record.' })}</p>
    {/if}
</div>
