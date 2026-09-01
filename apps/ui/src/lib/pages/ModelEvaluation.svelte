<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import {
        startModelEvalRun,
        listModelEvalRuns,
        getModelEvalRun,
        deleteModelEvalRun,
        cancelModelEvalRun,
        modelEvalArtifactUrl,
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
                try {
                    selectedRun = await getModelEvalRun(selectedRunId);
                } catch {
                    selectedRun = null;
                }
                try {
                    deviceMatrix = await getModelEvalDeviceMatrix(selectedRunId);
                } catch {
                    deviceMatrix = null;
                }
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
        if (!confirm(`Cancel run ${active.run_id}? Partial artifacts will be kept.`)) return;
        try {
            await cancelModelEvalRun(active.run_id);
            await refresh();
        } catch (e) {
            error = (e as Error).message;
        }
    }

    async function deleteRun(runId: string) {
        if (!confirm(`Delete eval run ${runId}? Artifacts will be removed.`)) return;
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

    let progressPct = $derived.by(() => {
        if (!active?.progress?.total) return 0;
        return Math.min(100, Math.round((active.progress.done / active.progress.total) * 100));
    });
</script>

<div class="space-y-6">
    {#if error}
        <div class="rounded-lg bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 p-3 text-red-800 dark:text-red-200">
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
                <div class="flex flex-wrap gap-1 text-xs">
                    <a class="text-brand-600 dark:text-brand-400 hover:underline" href={modelEvalArtifactUrl(selectedRun.run_id, 'summary.json')} target="_blank" rel="noopener">summary.json</a>
                    <span class="text-slate-400">·</span>
                    <a class="text-brand-600 dark:text-brand-400 hover:underline" href={modelEvalArtifactUrl(selectedRun.run_id, 'runtime.json')} target="_blank" rel="noopener">runtime.json</a>
                    <span class="text-slate-400">·</span>
                    <a class="text-brand-600 dark:text-brand-400 hover:underline" href={modelEvalArtifactUrl(selectedRun.run_id, 'confusions.csv')} target="_blank" rel="noopener">confusions.csv</a>
                </div>
            </header>

            {#if selectedRun.error}
                <div class="mt-3 rounded bg-red-50 dark:bg-red-900/30 border border-red-200 dark:border-red-700 p-2 text-sm text-red-800 dark:text-red-200">
                    Run failed: {selectedRun.error}
                </div>
            {/if}

            {#if selectedRun.models && selectedRun.models.length > 0}
                <div class="mt-4 overflow-x-auto">
                    <table class="min-w-full text-sm">
                        <thead class="text-xs uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700">
                            <tr>
                                <th class="text-left py-2 pr-4">Model</th>
                                <th class="text-right px-2">Top-1</th>
                                <th class="text-right px-2">Top-3</th>
                                <th class="text-right px-2">Core</th>
                                <th class="text-right px-2">Region</th>
                                <th class="text-right px-2">Mean</th>
                                <th class="text-right px-2">P95</th>
                                <th class="text-left pl-4">Provider</th>
                            </tr>
                        </thead>
                        <tbody>
                            {#each selectedRun.models as model (model.model_id)}
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
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(model.top1_accuracy)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(model.top3_accuracy)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(model.shared_core_top1)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{pct(model.regional_top1)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{ms(model.mean_latency_ms)}</td>
                                    <td class="text-right px-2 text-slate-700 dark:text-slate-300">{ms(model.p95_latency_ms)}</td>
                                    <td class="pl-4 text-xs text-slate-600 dark:text-slate-400">{model.active_provider ?? '—'}</td>
                                </tr>
                                {#if model.warnings && model.warnings.length > 0}
                                    <tr class="border-b border-slate-100 dark:border-slate-700">
                                        <td colspan="8" class="py-1 pr-4 pl-4 text-xs">
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
            {/if}

            {#if selectedRun.skipped_models && selectedRun.skipped_models.length > 0}
                <div class="mt-4 rounded-lg border border-amber-200 dark:border-amber-700 bg-amber-50 dark:bg-amber-900/20 p-3">
                    <h4 class="text-sm font-semibold text-amber-900 dark:text-amber-200">Skipped models</h4>
                    <ul class="mt-1 text-xs text-amber-800 dark:text-amber-300 space-y-1">
                        {#each selectedRun.skipped_models as s}
                            <li>
                                <span class="font-mono">{s.model_id}</span> — {s.reason}
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
                            onclick={() => { selectedRunId = row.run_id; refresh(); }}
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
