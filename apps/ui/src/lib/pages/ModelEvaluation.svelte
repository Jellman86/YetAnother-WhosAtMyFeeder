<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { confirmAction } from '../stores/confirm_dialog.svelte';
    import { isCompatibilityOnlyRun, modelEvalScores } from '../utils/model-eval-scores';
    import {
        startModelEvalRun,
        listModelEvalRuns,
        getModelEvalRun,
        deleteModelEvalRun,
        cancelModelEvalRun,
        fetchModelEvalArtifact,
        getModelEvalDeviceMatrix,
        type ModelEvalActiveStatus,
        type ModelEvalRunRow,
        type ModelEvalRunSummary,
        type ModelEvalModelSummary,
        type ModelEvalWarning,
        type DeviceMatrix,
    } from '../api/model_eval';

    let runs = $state<ModelEvalRunRow[]>([]);
    let active = $state<ModelEvalActiveStatus | null>(null);
    let selectedRunId = $state<string | null>(null);
    let selectedRun = $state<ModelEvalRunSummary | null>(null);
    let loading = $state(false);
    let error = $state<string | null>(null);
    let includePerImage = $state(false);
    let sweepDevices = $state(false);
    let deviceMatrix = $state<DeviceMatrix | null>(null);
    let pollHandle: number | null = null;
    let refreshInFlight = false;
    let downloadingArtifact = $state<string | null>(null);

    async function downloadArtifact(runId: string, artifact: string): Promise<void> {
        if (downloadingArtifact) return;
        downloadingArtifact = artifact;
        error = null;
        try {
            const blob = await fetchModelEvalArtifact(runId, artifact);
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = artifact;
            document.body.appendChild(link);
            try {
                link.click();
            } finally {
                link.remove();
                URL.revokeObjectURL(url);
            }
        } catch (cause) {
            error = cause instanceof Error ? cause.message : String(cause);
        } finally {
            downloadingArtifact = null;
        }
    }

    function matrixProviders(matrix: DeviceMatrix): string[] {
        return matrix.providers?.length ? matrix.providers : matrix.devices;
    }

    type MatrixRow = DeviceMatrix['models'][string] | NonNullable<DeviceMatrix['crop_detectors']>[string];

    function matrixRows(matrix: DeviceMatrix): Array<[string, MatrixRow]> {
        return [...Object.entries(matrix.models), ...Object.entries(matrix.crop_detectors ?? {})];
    }

    function deviceCell(row: MatrixRow | undefined, dev: string): { label: string; cls: string } {
        if (!row || row.error) return { label: '—', cls: 'text-slate-400' };
        const e = row.providers?.[dev] ?? row.devices?.[dev];
        if (!e) return { label: '—', cls: 'text-slate-400' };
        if (!e.compiles) return { label: '✗ fails', cls: 'text-red-600 dark:text-red-400' };
        if (e.finite === false) return { label: '⚠ NaN', cls: 'text-red-600 dark:text-red-400' };
        if (e.baseline || dev === row.baseline_provider || dev === 'CPU') return { label: `✓ baseline (${e.images_evaluated ?? 0})`, cls: 'text-slate-600 dark:text-slate-400' };
        const n = e.images_compared;
        if (row.comparison_kind === 'crop_box' && e.matches_cpu && n) {
            const iou = e.mean_box_iou;
            return { label: `✓ ${n}/${n} boxes${iou != null ? ` (${iou.toFixed(2)} IoU)` : ''}`, cls: 'text-accent-600 dark:text-accent-400' };
        }
        if (e.matches_cpu && n) return { label: `✓ ${n}/${n} top-1`, cls: 'text-accent-600 dark:text-accent-400' };
        if (typeof e.detection_match_rate === 'number' && n) {
            const hits = Math.round(e.detection_match_rate * n);
            const iou = e.mean_box_iou;
            return { label: `⚠ ${hits}/${n} boxes${iou != null ? ` (${iou.toFixed(2)} IoU)` : ''}`, cls: 'text-amber-600 dark:text-amber-400' };
        }
        if (typeof e.top1_match_rate === 'number' && n) {
            const hits = Math.round(e.top1_match_rate * n);
            const ov = e.mean_top5_overlap;
            return { label: `⚠ ${hits}/${n} top-1${ov != null ? ` (${ov}/5)` : ''}`, cls: 'text-amber-600 dark:text-amber-400' };
        }
        return { label: '✓ runs', cls: 'text-accent-600 dark:text-accent-400' };
    }

    function providerName(provider: string | null | undefined): string {
        if (!provider) return '—';
        const labels: Record<string, string> = {
            cpu: $_('settings.detection.provider_cpu', { default: 'CPU (ONNX Runtime)' }),
            cuda: $_('settings.detection.provider_cuda', { default: 'NVIDIA CUDA' }),
            intel_gpu: $_('settings.detection.provider_intel_gpu', { default: 'Intel GPU (OpenVINO)' }),
            intel_cpu: $_('settings.detection.provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' }),
            intel_npu: $_('settings.detection.provider_intel_npu', { default: 'Intel NPU (OpenVINO)' }),
        };
        return labels[provider] ?? provider;
    }

    // A compatibility-only run writes summary.json and device_matrix.json; the
    // accuracy artifacts exist only for a full evaluation.
    function runArtifacts(compatibilityOnly: boolean, matrix: DeviceMatrix | null): string[] {
        if (!compatibilityOnly) return ['summary.json', 'runtime.json', 'confusions.csv'];
        return matrix ? ['summary.json', 'device_matrix.json'] : ['summary.json'];
    }

    function pct(value: number | null | undefined): string {
        if (value === null || value === undefined || Number.isNaN(value)) return '—';
        return `${(value * 100).toFixed(1)}%`;
    }
    function ms(value: number | null | undefined): string {
        if (value === null || value === undefined || Number.isNaN(value)) return '—';
        return `${value.toFixed(0)} ms`;
    }
    function ratio(value: number | null | undefined): string {
        if (value === null || value === undefined || Number.isNaN(value)) return '—';
        return `${value.toFixed(2)}×`;
    }
    function severityColor(severity: ModelEvalWarning['severity']): string {
        if (severity === 'critical') return 'text-red-600 dark:text-red-400';
        if (severity === 'warning') return 'text-amber-600 dark:text-amber-400';
        return 'text-brand-600 dark:text-brand-400';
    }

    // Only the newest selection may land: a slow reply for a run the owner has
    // since moved away from must not replace the run they are looking at.
    let selectionRequest = 0;

    async function loadSelectedRun(runId: string): Promise<void> {
        const request = ++selectionRequest;
        const [summary, matrix] = await Promise.all([
            getModelEvalRun(runId).catch(() => null),
            getModelEvalDeviceMatrix(runId).catch(() => null),
        ]);
        if (request !== selectionRequest || runId !== selectedRunId) return;
        selectedRun = summary;
        deviceMatrix = matrix;
    }

    function selectRun(runId: string): void {
        if (runId !== selectedRunId) {
            selectedRun = null;
            deviceMatrix = null;
            error = null;
        }
        selectedRunId = runId;
        void loadSelectedRun(runId);
    }

    async function refresh() {
        if (refreshInFlight) return;
        refreshInFlight = true;
        try {
            const list = await listModelEvalRuns();
            runs = list.runs;
            active = list.active;
            if (!selectedRunId && runs.length > 0) {
                selectedRunId = runs[0].run_id;
            }
            if (selectedRunId) {
                await loadSelectedRun(selectedRunId);
            }
        } catch (e) {
            error = (e as Error).message;
        } finally {
            refreshInFlight = false;
        }
    }

    function startPolling() {
        if (pollHandle) return;
        pollHandle = window.setInterval(() => {
            if (!document.hidden) void refresh();
        }, 2000);
    }
    function stopPolling() {
        if (pollHandle) {
            clearInterval(pollHandle);
            pollHandle = null;
        }
    }

    $effect(() => {
        if (active) startPolling();
        else stopPolling();
    });

    async function startRun() {
        loading = true;
        error = null;
        try {
            const { run_id } = await startModelEvalRun({ include_per_image: includePerImage, sweep_devices: sweepDevices });
            selectedRunId = run_id;
            await refresh();
            startPolling();
        } catch (e) {
            error = (e as Error).message;
        } finally {
            loading = false;
        }
    }

    async function cancelRun() {
        if (!active) return;
        const runId = active.run_id;
        const confirmed = await confirmAction({
            title: 'Cancel evaluation run',
            message: `Cancel run ${runId}? Partial artifacts will be kept.`,
            confirmLabel: 'Cancel run'
        });
        if (!confirmed) return;
        try {
            await cancelModelEvalRun(runId);
            await refresh();
        } catch (e) {
            error = (e as Error).message;
        }
    }

    async function deleteRun(runId: string) {
        const confirmed = await confirmAction({
            title: 'Delete evaluation run',
            message: `Delete eval run ${runId}? Artifacts will be removed.`,
            confirmLabel: 'Delete run'
        });
        if (!confirmed) return;
        try {
            await deleteModelEvalRun(runId);
            if (selectedRunId === runId) {
                selectedRunId = null;
                selectedRun = null;
            }
            await refresh();
        } catch (e) {
            error = (e as Error).message;
        }
    }

    onMount(refresh);
    onDestroy(stopPolling);

    let compatibilityOnly = $derived(isCompatibilityOnlyRun(selectedRun?.models));
    let artifacts = $derived(runArtifacts(compatibilityOnly, deviceMatrix));

    let progressPct = $derived.by(() => {
        if (!active?.progress?.total) return 0;
        return Math.min(100, Math.round((active.progress.done / active.progress.total) * 100));
    });
</script>

<div class="space-y-6">
    {#if error}
        <div role="alert" class="rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 p-3 text-red-800 dark:text-red-200">
            {error}
        </div>
    {/if}

    <section class="rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-5">
        <h2 class="text-lg font-semibold text-slate-900 dark:text-slate-100">Model Evaluation</h2>
        <p class="mt-1 text-sm text-slate-600 dark:text-slate-400">
            Run every installed classifier against auto-fetched, taxonomy-verified bird images
            from iNaturalist (with Wikimedia Commons fallback). Progress is reported live; full
            artifacts persist under <code class="px-1 rounded bg-slate-100 dark:bg-slate-900">/config/yawamf-eval/&lt;run_id&gt;/</code>.
        </p>

        <div class="mt-4 flex flex-wrap items-center gap-3">
            <label class="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
                <input type="checkbox" bind:checked={includePerImage} class="rounded" />
                Include per-image details (results.jsonl)
            </label>
            <label class="inline-flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300" title="Downloads every registry model, then validates each provider owned by this image against the CPU baseline. Slower.">
                <input type="checkbox" bind:checked={sweepDevices} class="rounded" />
                Sweep image providers (auto-downloads all models)
            </label>
            <button
                type="button"
                disabled={!!active || loading}
                onclick={startRun}
                class="btn btn-primary min-h-11 px-4 py-2 text-sm"
            >
                {active ? 'Run in progress…' : 'Run Evaluation'}
            </button>
            {#if active}
                <button
                    type="button"
                    onclick={cancelRun}
                    class="btn btn-secondary min-h-11 px-4 py-2 text-sm text-red-600 dark:text-red-400"
                >
                    Cancel
                </button>
            {/if}
        </div>

        {#if active}
            <div class="mt-4">
                <div class="flex justify-between text-xs text-slate-600 dark:text-slate-400">
                    <span>{active.phase} · {active.progress.label}</span>
                    <span>{active.progress.done} / {active.progress.total} ({progressPct}%)</span>
                </div>
                <div class="mt-1 h-2 rounded-full bg-slate-200 dark:bg-slate-700 overflow-hidden">
                    <div class="h-full bg-brand-500 transition-all" style="width: {progressPct}%"></div>
                </div>
            </div>
        {/if}
    </section>

    {#if selectedRun}
        <section class="rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-5">
            <header class="flex items-start justify-between flex-wrap gap-2">
                <div>
                    <h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">
                        Run {selectedRun.run_id}
                    </h3>
                    <p class="text-xs text-slate-500 dark:text-slate-400">
                        {#if selectedRun.test_set}
                            {selectedRun.test_set.total_species} species · {selectedRun.test_set.total_images} images · region {selectedRun.test_set.region ?? '—'}
                        {/if}
                        {#if selectedRun.duration_seconds}
                            · {Math.round(selectedRun.duration_seconds / 60)} min
                        {/if}
                    </p>
                </div>
                <div class="flex flex-wrap gap-1 text-xs" aria-busy={downloadingArtifact !== null}>
                    {#each artifacts as artifact (artifact)}
                        <button
                            type="button"
                            class="btn btn-ghost min-h-11 px-2 text-xs"
                            disabled={downloadingArtifact !== null}
                            onclick={() => selectedRun && downloadArtifact(selectedRun.run_id, artifact)}
                        >
                            {#if downloadingArtifact === artifact}
                                <span class="h-3 w-3 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none" aria-hidden="true"></span>
                            {/if}
                            {artifact}
                        </button>
                    {/each}
                </div>
            </header>

            {#if selectedRun.error}
                <div class="mt-3 rounded bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 p-2 text-sm text-red-800 dark:text-red-200">
                    Run failed: {selectedRun.error}
                </div>
            {/if}

            {#if compatibilityOnly && selectedRun.models}
                <div class="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-3 dark:border-slate-700 dark:bg-slate-900/40">
                    <h4 class="text-sm font-semibold text-slate-900 dark:text-slate-100">
                        {$_('model_eval.compat_only_title', { default: 'Compatibility check only' })}
                    </h4>
                    <p class="mt-1 text-xs text-slate-600 dark:text-slate-400">
                        {$_('model_eval.compat_only_body', { default: 'This run checked that each provider loads, gives finite output and agrees with the CPU baseline. It did not measure accuracy, so no accuracy figures are shown. Run Evaluation to measure accuracy.' })}
                    </p>
                </div>
                <div class="mt-4 overflow-x-auto">
                    <table class="min-w-full text-sm">
                        <thead class="text-xs uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                            <tr>
                                <th class="text-left py-2 pr-4">{$_('model_eval.col_model', { default: 'Model' })}</th>
                                <th class="text-left px-2">{$_('model_eval.col_best_provider', { default: 'Best validated provider' })}</th>
                                <th class="text-right px-2">{$_('model_eval.col_median_inference', { default: 'Median inference' })}</th>
                                <th class="text-left pl-4">{$_('model_eval.col_validated_providers', { default: 'Validated providers' })}</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each selectedRun.models as model (model.model_id)}
                                <tr class="border-b border-slate-100 dark:border-slate-700">
                                    <td class="py-2 pr-4 font-mono text-xs text-slate-900 dark:text-slate-100">{model.model_id}</td>
                                    <td class="px-2 text-slate-700 dark:text-slate-300">{model.ready ? providerName(model.active_provider) : '—'}</td>
                                    <!-- Every latency field of a compatibility row holds the best provider's median. -->
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{ms(model.p50_latency_ms ?? model.mean_latency_ms)}</td>
                                    <td class="pl-4 text-xs text-slate-600 dark:text-slate-400">
                                        {model.validated_providers?.length ? model.validated_providers.map(providerName).join(', ') : '—'}
                                    </td>
                                </tr>
                                {#if model.warnings && model.warnings.length > 0}
                                    <tr class="border-b border-slate-100 dark:border-slate-700">
                                        <td colspan="4" class="py-1 pr-4 pl-4 text-xs">
                                            {#each model.warnings as w}
                                                <div class={severityColor(w.severity)}>
                                                    <span class="font-mono">{w.code}</span>: {w.message}
                                                </div>
                                            {/each}
                                        </td>
                                    </tr>
                                {/if}
                            {/each}
                        </tbody>
                    </table>
                </div>
            {:else if selectedRun.models && selectedRun.models.length > 0}
                <div class="mt-4 overflow-x-auto">
                    <table class="min-w-full text-sm">
                        <thead class="text-xs uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                            <tr>
                                <th class="text-left py-2 pr-4">Model</th>
                                <th class="text-right px-2">Top-1</th>
                                <th class="text-right px-2">Top-3</th>
                                <th class="text-right px-2">Core</th>
                                <th class="text-right px-2">Region</th>
                                <th class="text-right px-2">Can name</th>
                                <th class="text-right px-2">Mean</th>
                                <th class="text-right px-2">P95</th>
                                <th class="text-left pl-4">Provider</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each selectedRun.models as model (model.model_id)}
                                {@const scores = modelEvalScores(model)}
                                <tr class="border-b border-slate-100 dark:border-slate-700">
                                    <td class="py-2 pr-4 font-mono text-xs text-slate-900 dark:text-slate-100">
                                        {model.model_id}
                                        {#if model.warnings && model.warnings.length > 0}
                                            <span class="ml-1 inline-flex items-center text-xs">
                                                {#each model.warnings as w}
                                                    <span class={severityColor(w.severity)} title={w.message}>⚠</span>
                                                {/each}
                                            </span>
                                        {/if}
                                    </td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(scores.top1)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(scores.top3)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(scores.core)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(scores.region)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300 whitespace-nowrap">{scores.canName ?? '—'}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{ms(model.mean_latency_ms)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{ms(model.p95_latency_ms)}</td>
                                    <td class="pl-4 text-xs text-slate-600 dark:text-slate-400">{model.active_provider ?? '—'}</td>
                                </tr>
                                {#if model.warnings && model.warnings.length > 0}
                                    <tr class="border-b border-slate-100 dark:border-slate-700">
                                        <td colspan="9" class="py-1 pr-4 pl-4 text-xs">
                                            {#each model.warnings as w}
                                                <div class={severityColor(w.severity)}>
                                                    <span class="font-mono">{w.code}</span>: {w.message}
                                                </div>
                                            {/each}
                                        </td>
                                    </tr>
                                {/if}
                            {/each}
                        </tbody>
                    </table>
                </div>
                {#if selectedRun.models.some((model) => model.vocabulary_known)}
                    <p class="mt-2 text-xs text-slate-500 dark:text-slate-400">
                        Accuracy counts only the test species each model can name, shown under Can name. A regional model is not marked down for birds outside its region.
                    </p>
                {/if}
            {/if}

            {#if selectedRun.skipped_models && selectedRun.skipped_models.length > 0}
                <div class="mt-4 rounded-lg border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-3">
                    <h4 class="text-sm font-semibold text-amber-900 dark:text-amber-200">Skipped models</h4>
                    <ul class="mt-1 text-xs text-amber-800 dark:text-amber-300 space-y-1">
                        {#each selectedRun.skipped_models as s}
                            <li>
                                <span class="font-mono">{s.model_id}</span>: {s.reason}
                                {#if s.detail}<span class="text-amber-700 dark:text-amber-400 italic"> ({s.detail})</span>{/if}
                            </li>
                        {/each}
                    </ul>
                </div>
            {/if}
        </section>
    {/if}

    {#if deviceMatrix}
        <section class="rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-5">
            <h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">Provider compatibility matrix</h3>
            <p class="mt-1 text-xs text-slate-600 dark:text-slate-400">
                Image {deviceMatrix.image_flavor ?? 'unknown'} tested each packaged, detected, and
                model-compatible provider in an isolated subprocess. Accelerators are compared with
                the CPU baseline on {deviceMatrix.image_count ?? 0} varied real bird images. Classifiers
                compare ranking; crop detectors compare detection presence, box geometry and confidence,
                with three additional hard-negative images.
            </p>
            <div class="mt-3 overflow-x-auto">
                <table class="w-full text-sm">
                    <thead class="text-xs uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                        <tr>
                            <th class="text-left py-2 pr-4">Model</th>
                            {#each matrixProviders(deviceMatrix) as dev}
                                <th class="text-left px-2">{dev}</th>
                            {/each}
                        </tr>
                    </thead>
                    <tbody>
                        {#each matrixRows(deviceMatrix) as [modelId, row]}
                            <tr class="border-b border-slate-100 dark:border-slate-800">
                                <td class="py-2 pr-4 font-medium text-slate-800 dark:text-slate-200">
                                    {modelId}{#if row.comparison_kind === 'crop_box'} <span class="text-slate-400">· crop detector</span>{/if}
                                </td>
                                {#each matrixProviders(deviceMatrix) as dev}
                                    {@const c = deviceCell(row, dev)}
                                    <td class="px-2 text-xs {c.cls}">{c.label}</td>
                                {/each}
                            </tr>
                        {/each}
                    </tbody>
                </table>
            </div>
        </section>
    {/if}

    <section class="rounded-xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-5">
        <h3 class="text-base font-semibold text-slate-900 dark:text-slate-100">Run history</h3>
        {#if runs.length === 0}
            <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">No runs yet.</p>
        {:else}
            <ul class="mt-2 divide-y divide-slate-200 dark:divide-slate-700">
                {#each runs as row (row.run_id)}
                    <li class="py-2 flex items-center justify-between text-sm">
                        <button
                            type="button"
                            onclick={() => selectRun(row.run_id)}
                            class="btn btn-ghost min-h-11 flex-1 justify-start px-2 py-1 text-left hover:text-brand-600 dark:hover:text-brand-400"
                        >
                            <span class="font-mono">{row.run_id}</span>
                            <span class="ml-2 text-xs text-slate-500 dark:text-slate-400">
                                {#if row.duration_seconds}{Math.round(row.duration_seconds / 60)} min · {/if}
                                {row.model_count ?? 0} models · {row.total_species ?? 0} species
                                {#if row.region} · {row.region}{/if}
                                {#if row.error} · <span class="text-red-600 dark:text-red-400">error</span>{/if}
                            </span>
                        </button>
                        <button
                            type="button"
                            onclick={() => deleteRun(row.run_id)}
                            class="btn btn-ghost ml-4 min-h-11 px-2 py-1 text-xs text-slate-500 hover:text-red-600 dark:text-slate-400 dark:hover:text-red-400"
                            disabled={row.run_id === active?.run_id}
                        >
                            Delete
                        </button>
                    </li>
                {/each}
            </ul>
        {/if}
    </section>
</div>
