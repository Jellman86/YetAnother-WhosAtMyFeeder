<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { LlmTestResult } from '../../api/maintenance';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import type { DiagnosticStage, DiagnosticResult } from '../../utils/diagnostic-runner';

    let {
        provider,
        model,
        running,
        result,
        runId = 0,
        onClose,
        onRetry
    }: {
        provider: string;
        model: string;
        running: boolean;
        result: LlmTestResult | null;
        runId?: number;
        onClose: () => void;
        onRetry: () => void;
    } = $props();

    const stageDefinitions = $derived([
        { id: 'configuration' as const, label: $_('settings.ai.test_stage_configuration', { default: 'Configuration' }) },
        { id: 'provider' as const, label: $_('settings.ai.test_stage_provider', { default: 'Provider availability' }) },
        { id: 'vision' as const, label: $_('settings.ai.test_stage_vision', { default: 'Vision input' }) },
        { id: 'multi_frame' as const, label: $_('settings.ai.test_stage_multiframe', { default: 'Multi-frame request' }) },
        { id: 'response' as const, label: $_('settings.ai.test_stage_response', { default: 'Model response' }) }
    ]);

    // The backend returns a single result carrying the stage it reached, so we
    // map that onto per-stage truth. Everything is `pending` until the result
    // lands; DiagnosticDialog then reveals the resolved stages one at a time.
    const stages = $derived.by((): DiagnosticStage[] => {
        if (!result) {
            return stageDefinitions.map((stage) => ({
                ...stage,
                state: 'pending',
                message: $_('settings.ai.test_pending', { default: 'Waiting for the provider response.' })
            }));
        }

        if (result.status === 'ok') {
            return stageDefinitions.map((stage) => ({
                ...stage,
                state: 'passed',
                message: stage.id === 'multi_frame'
                    ? $_('settings.ai.test_multiframe_ok', {
                        values: { count: result.frame_count },
                        default: `${result.frame_count} JPEG frames were accepted in one request.`
                    })
                    : $_('settings.ai.test_stage_ok', { default: 'Passed' })
            }));
        }

        const failureIndex = Math.max(0, stageDefinitions.findIndex((stage) => stage.id === result.failure_stage));
        return stageDefinitions.map((stage, index) => ({
            ...stage,
            state: index < failureIndex ? 'passed' : index === failureIndex ? 'failed' : 'skipped',
            message: index < failureIndex
                ? $_('settings.ai.test_stage_ok', { default: 'Passed' })
                : index === failureIndex
                    ? result.message
                    : $_('settings.ai.test_skipped', { default: 'Not run because an earlier stage failed.' })
        }));
    });

    const diagnosticResult = $derived.by((): DiagnosticResult | null => {
        if (!result) return null;
        return {
            ok: result.status === 'ok',
            message: result.message,
            hint: result.retry_after_seconds
                ? $_('settings.ai.test_retry_after', {
                    values: { seconds: result.retry_after_seconds },
                    default: `Provider suggested retrying after ${result.retry_after_seconds} seconds.`
                })
                : undefined
        };
    });
</script>

<DiagnosticDialog
    title={$_('settings.ai.test_title', { default: 'AI model diagnostic' })}
    subtitle={$_('settings.ai.test_subtitle', { default: 'Checking the same multi-frame vision format used for detection analysis.' })}
    {stages}
    busy={running}
    result={diagnosticResult}
    {runId}
    note={$_('settings.ai.test_probe_note', { default: 'This sends five representative 1280×720 JPEG frames, matching the count, dimensions, and approximate payload size of a real analysis request.' })}
    retryLabel={$_('settings.ai.test_retry', { default: 'Run test again' })}
    runningLabel={$_('settings.ai.test_running', { default: 'Testing' })}
    {onClose}
    {onRetry}
>
    {#snippet summary()}
        <span class="text-[10px] font-black uppercase tracking-widest text-slate-400">{$_('settings.llm.provider')}</span>
        <span class="font-bold text-slate-800 dark:text-slate-100">{provider}</span>
        <span class="text-slate-300 dark:text-slate-600" aria-hidden="true">·</span>
        <span class="text-[10px] font-black uppercase tracking-widest text-slate-400">{$_('settings.llm.model')}</span>
        <span class="min-w-0 truncate font-bold text-slate-800 dark:text-slate-100" title={model}>{model}</span>
    {/snippet}
</DiagnosticDialog>
