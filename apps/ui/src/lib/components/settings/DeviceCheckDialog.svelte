<script lang="ts">
    import { _ } from 'svelte-i18n';
    import DiagnosticDialog from '../DiagnosticDialog.svelte';
    import type { DiagnosticResult, DiagnosticStage, DiagnosticStageState } from '../../utils/diagnostic-runner';
    import type { DeviceMatrix } from '../../api/model_eval';
    import { deviceCheckProblemText, type DeviceCheck } from '../../settings/device-check.svelte';
    import { compatEntry, compatProviders, compatRows, INFERENCE_PROVIDER_LABELS, isInferenceProvider, type CompatRow } from '../../settings/device-matrix';

    // The device check through the shared DiagnosticDialog: one stage per device, aggregated from
    // the matrix. `warning` is honest for a device that runs but whose results differ from the CPU.
    let { check }: { check: DeviceCheck } = $props();

    function providerLabel(provider: string): string {
        if (!isInferenceProvider(provider)) return provider;
        const label = INFERENCE_PROVIDER_LABELS[provider];
        return $_(label.key, { default: label.fallback });
    }

    function cellOutcome(row: CompatRow | undefined, device: string): { state: DiagnosticStageState; note: string } {
        if (!row || row.error) return { state: 'skipped', note: '—' };
        const entry = compatEntry(row, device);
        if (!entry) return { state: 'skipped', note: '—' };
        if (!entry.compiles) return { state: 'failed', note: $_('settings.detection.compat_note_fails', { default: 'fails to compile' }) };
        if (entry.finite === false) return { state: 'failed', note: $_('settings.detection.compat_note_nan', { default: 'non-finite output' }) };
        if (entry.baseline || device === row.baseline_provider || device === 'CPU') return { state: 'passed', note: $_('settings.detection.compat_note_baseline', { default: 'CPU baseline' }) };
        const n = entry.images_compared;
        if (entry.matches_cpu && n) return { state: 'passed', note: $_('settings.detection.compat_note_match', { default: '{n}/{n} match CPU', values: { n } }) };
        if (typeof entry.detection_match_rate === 'number' && n) {
            return { state: 'warning', note: $_('settings.detection.compat_note_boxes', { default: '{m}/{n} boxes match CPU', values: { m: Math.round(entry.detection_match_rate * n), n } }) };
        }
        if (typeof entry.top1_match_rate === 'number' && n) {
            return { state: 'warning', note: $_('settings.detection.compat_note_partial', { default: '{m}/{n} match CPU', values: { m: Math.round(entry.top1_match_rate * n), n } }) };
        }
        return { state: 'passed', note: $_('settings.detection.compat_note_runs', { default: 'runs' }) };
    }

    const STATE_RANK: Record<DiagnosticStageState, number> = { pending: 0, running: 0, skipped: 1, passed: 2, warning: 3, failed: 4 };

    function deviceStage(matrix: DeviceMatrix, device: string): DiagnosticStage {
        let state: DiagnosticStageState = 'skipped';
        const parts: string[] = [];
        for (const [model, row] of compatRows(matrix)) {
            const outcome = cellOutcome(row, device);
            if (STATE_RANK[outcome.state] > STATE_RANK[state]) state = outcome.state;
            parts.push(`${model}: ${outcome.note}`);
        }
        return { id: device, label: providerLabel(device), state, message: parts.join(' · ') };
    }

    const stages = $derived.by((): DiagnosticStage[] => {
        const matrix = check.matrix;
        if (!matrix) {
            return [{
                id: 'run',
                label: $_('settings.detection.compat_stage_run', { default: "Validating this host's devices" }),
                state: check.running ? 'running' : 'pending',
                message: check.progress
                    ? `${check.progress.done}/${check.progress.total} · ${check.progress.label}`
                    : $_('settings.detection.compat_stage_run_hint', { default: 'Compiling and comparing each device against the CPU baseline…' })
            }];
        }
        return compatProviders(matrix).map((device) => deviceStage(matrix, device));
    });

    const result = $derived.by((): DiagnosticResult | null => {
        if (check.problem) return { ok: false, message: deviceCheckProblemText(check.problem, $_) };
        if (!check.matrix) return null;
        const failed = stages.some((stage) => stage.state === 'failed');
        const warned = stages.some((stage) => stage.state === 'warning');
        const skipped = stages.some((stage) => stage.state === 'skipped');
        return {
            ok: !failed && !warned && !skipped,
            message: failed
                ? $_('settings.detection.compat_result_failed', { default: 'Some devices failed validation. See the breakdown below.' })
                : skipped
                    ? $_('settings.detection.compat_result_skipped', { default: 'Some devices could not be validated. See the breakdown below.' })
                    : warned
                        ? $_('settings.detection.compat_result_warn', { default: 'All devices run, but some differ from the CPU baseline.' })
                        : $_('settings.detection.compat_result_ok', { default: 'All devices match the CPU baseline.' })
        };
    });
</script>

{#if check.dialogOpen}
    <DiagnosticDialog
        title={$_('settings.detection.compat_test_title', { default: 'Device compatibility check' })}
        subtitle={$_('settings.detection.compat_test_subtitle', { default: 'Validates every provider available to this image and model against the CPU baseline.' })}
        {stages}
        busy={check.running}
        {result}
        runId={check.dialogRunId}
        retryLabel={$_('settings.detection.compat_run', { default: 'Check devices for every installed model' })}
        onClose={() => (check.dialogOpen = false)}
        onRetry={() => check.retry()}
    />
{/if}
