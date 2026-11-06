<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { GardenCapture, GardenPhotoCheck } from '../api/garden';
    import { withAuthParams } from '../api/core';
    import type { DiagnosticStage, DiagnosticResult } from '../utils/diagnostic-runner';
    import DiagnosticDialog from './DiagnosticDialog.svelte';

    let { capture, assessment, busy, error, runId, size, onClose }: {
        capture: GardenCapture;
        assessment: GardenPhotoCheck | null;
        busy: boolean;
        error: string | null;
        runId: number;
        size: readonly [number, number];
        onClose: () => void;
    } = $props();
    const message = $derived.by(() => {
        if (error) return error;
        if (!assessment) return $_('garden.check_running', { default: 'Checking this crop. Bird work takes priority.' });
        if (assessment.suggestion === 'bird') return $_('garden.check_bird', { default: 'Model suggests a bird' });
        if (assessment.suggestion === 'mammal') return $_('garden.check_mammal', { default: 'Model suggests a non-human mammal' });
        if (assessment.suggestion === 'unavailable') return $_('garden.check_unavailable', { default: 'Photo check unavailable. Review the photo yourself.' });
        return $_('garden.check_uncertain', { default: 'The model is uncertain. Review the photo yourself.' });
    });
    const stages = $derived<DiagnosticStage[]>([{
        id: 'photo-assessment', label: $_('garden.check_assessment', { default: 'Model assessment' }),
        state: busy ? 'running' : error ? 'failed' : 'warning', message
    }]);
    const result = $derived<DiagnosticResult | null>(busy ? null : {
        ok: false, message, hint: $_('garden.check_advisory', { default: 'This photo only. Confirm or dismiss it yourself; no review decision has been saved.' })
    });
    const scores = $derived.by(() => {
        if (!assessment?.mass) return '';
        const percent = new Intl.NumberFormat(undefined, { style: 'percent', maximumFractionDigits: 1 });
        return $_('garden.check_scores', {
            default: 'Bird {bird} · Non-human mammal {mammal} · Human {human} · Blank {blank} · Other {other}',
            values: Object.fromEntries(Object.entries(assessment.mass).map(([key, value]) => [key, percent.format(value)]))
        });
    });
</script>

{#snippet summary()}
    <div class="space-y-2">
        {#if capture.snapshot_url && capture.motion_source}
            {@const box = capture.motion_source.box_xywh}
            <div class="relative aspect-video w-full max-h-48 rounded-lg bg-surface-raised">
                <img src={withAuthParams(capture.snapshot_url)} alt={$_('garden.photo_alt', { default: 'Animal capture from {camera}', values: { camera: capture.camera } })} class="absolute inset-0 h-full w-full object-contain rounded-lg" />
                <svg class="pointer-events-none absolute inset-0 h-full w-full text-amber-400" viewBox={`0 0 ${size[0]} ${size[1]}`} preserveAspectRatio="xMidYMid meet" aria-hidden="true" data-garden-check-input>
                    <rect x={Math.trunc(box[0] * size[0])} y={Math.trunc(box[1] * size[1])} width={Math.trunc(box[2] * size[0])} height={Math.trunc(box[3] * size[1])} fill="none" stroke="black" stroke-width="4" vector-effect="non-scaling-stroke" />
                    <rect x={Math.trunc(box[0] * size[0])} y={Math.trunc(box[1] * size[1])} width={Math.trunc(box[2] * size[0])} height={Math.trunc(box[3] * size[1])} fill="none" stroke="currentColor" stroke-width="2" vector-effect="non-scaling-stroke" />
                </svg>
            </div>
        {/if}
        <p class="text-sm">{capture.camera} · {new Date(capture.observed_at).toLocaleString()}</p>
        {#if assessment}
            <p class="text-xs">{assessment.variant} · {assessment.devices.join(', ')}</p>
            {#if scores}<p class="text-xs break-words">{scores}</p>{/if}
        {/if}
    </div>
{/snippet}

<DiagnosticDialog title={$_('garden.check_photo', { default: 'Check photo' })}
    subtitle={$_('garden.check_help', { default: 'An advisory assessment of the highlighted crop, without confirming animal presence.' })}
    {stages} {result} {busy} {summary} {runId} {onClose}
    runningLabel={$_('garden.working', { default: 'Working…' })} />
