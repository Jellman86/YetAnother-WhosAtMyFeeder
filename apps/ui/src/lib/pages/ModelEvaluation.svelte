<script lang="ts">
    import { onMount, onDestroy } from 'svelte';
    import {
        startModelEvalRun,
        listModelEvalRuns,
        getModelEvalRun,
        deleteModelEvalRun,
        modelEvalArtifactUrl,
        type ModelEvalActiveStatus,
        type ModelEvalRunRow,
        type ModelEvalRunSummary,
        type ModelEvalModelSummary,
        type ModelEvalWarning,
    } from '../api/model_eval';

    let runs = $state<ModelEvalRunRow[]>([]);
    let active = $state<ModelEvalActiveStatus | null>(null);
    let selectedRunId = $state<string | null>(null);
    let selectedRun = $state<ModelEvalRunSummary | null>(null);
    let loading = $state(false);
    let error = $state<string | null>(null);
    let includePerImage = $state(false);
    let pollHandle: number | null = null;

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
        return 'text-blue-600 dark:text-blue-400';
    }

    async function refresh() {
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
            }
        } catch (e) {
            error = (e as Error).message;
        }
    }

    function startPolling() {
        if (pollHandle) return;
        pollHandle = window.setInterval(refresh, 2000);
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
            const { run_id } = await startModelEvalRun({ include_per_image: includePerImage });
            selectedRunId = run_id;
            await refresh();
            startPolling();
        } catch (e) {
            error = (e as Error).message;
        } finally {
            loading = false;
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

    <section class="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-5">
        <h2 class="text-lg font-semibold text-gray-900 dark:text-gray-100">Model Evaluation</h2>
        <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
            Run every installed classifier against auto-fetched, taxonomy-verified bird images
            from iNaturalist (with Wikimedia Commons fallback). Progress is reported live; full
            artifacts persist under <code class="px-1 rounded bg-gray-100 dark:bg-gray-900">/config/yawamf-eval/&lt;run_id&gt;/</code>.
        </p>

        <div class="mt-4 flex flex-wrap items-center gap-3">
            <label class="inline-flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
                <input type="checkbox" bind:checked={includePerImage} class="rounded" />
                Include per-image details (results.jsonl)
            </label>
            <button
                type="button"
                disabled={!!active || loading}
                onclick={startRun}
                class="px-4 py-2 rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:bg-gray-400 dark:disabled:bg-gray-700 disabled:cursor-not-allowed text-sm font-medium"
            >
                {active ? 'Run in progress…' : 'Run Evaluation'}
            </button>
        </div>

        {#if active}
            <div class="mt-4">
                <div class="flex justify-between text-xs text-gray-600 dark:text-gray-400">
                    <span>{active.phase} · {active.progress.label}</span>
                    <span>{active.progress.done} / {active.progress.total} ({progressPct}%)</span>
                </div>
                <div class="mt-1 h-2 rounded-full bg-gray-200 dark:bg-gray-700 overflow-hidden">
                    <div class="h-full bg-blue-500 transition-all" style="width: {progressPct}%"></div>
                </div>
            </div>
        {/if}
    </section>

    {#if selectedRun}
        <section class="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-5">
            <header class="flex items-start justify-between flex-wrap gap-2">
                <div>
                    <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">
                        Run {selectedRun.run_id}
                    </h3>
                    <p class="text-xs text-gray-500 dark:text-gray-400">
                        {#if selectedRun.test_set}
                            {selectedRun.test_set.total_species} species · {selectedRun.test_set.total_images} images · region {selectedRun.test_set.region ?? '—'}
                        {/if}
                        {#if selectedRun.duration_seconds}
                            · {Math.round(selectedRun.duration_seconds / 60)} min
                        {/if}
                    </p>
                </div>
                <div class="flex flex-wrap gap-1 text-xs">
                    <a class="text-blue-600 dark:text-blue-400 hover:underline" href={modelEvalArtifactUrl(selectedRun.run_id, 'summary.json')} target="_blank" rel="noopener">summary.json</a>
                    <span class="text-gray-400">·</span>
                    <a class="text-blue-600 dark:text-blue-400 hover:underline" href={modelEvalArtifactUrl(selectedRun.run_id, 'runtime.json')} target="_blank" rel="noopener">runtime.json</a>
                    <span class="text-gray-400">·</span>
                    <a class="text-blue-600 dark:text-blue-400 hover:underline" href={modelEvalArtifactUrl(selectedRun.run_id, 'confusions.csv')} target="_blank" rel="noopener">confusions.csv</a>
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
                        <thead class="text-xs uppercase text-gray-500 dark:text-gray-400 border-b border-gray-200 dark:border-gray-700">
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
                                <tr class="border-b border-gray-100 dark:border-gray-700">
                                    <td class="py-2 pr-4 font-mono text-xs text-gray-900 dark:text-gray-100">
                                        {model.model_id}
                                        {#if model.warnings && model.warnings.length > 0}
                                            <span class="ml-1 inline-flex items-center text-xs">
                                                {#each model.warnings as w}
                                                    <span class={severityColor(w.severity)} title={w.message}>⚠</span>
                                                {/each}
                                            </span>
                                        {/if}
                                    </td>
                                    <td class="text-right px-2 text-gray-700 dark:text-gray-300">{pct(model.top1_accuracy)}</td>
                                    <td class="text-right px-2 text-gray-700 dark:text-gray-300">{pct(model.top3_accuracy)}</td>
                                    <td class="text-right px-2 text-gray-700 dark:text-gray-300">{pct(model.shared_core_top1)}</td>
                                    <td class="text-right px-2 text-gray-700 dark:text-gray-300">{pct(model.regional_top1)}</td>
                                    <td class="text-right px-2 text-gray-700 dark:text-gray-300">{ms(model.mean_latency_ms)}</td>
                                    <td class="text-right px-2 text-gray-700 dark:text-gray-300">{ms(model.p95_latency_ms)}</td>
                                    <td class="pl-4 text-xs text-gray-600 dark:text-gray-400">{model.active_provider ?? '—'}</td>
                                </tr>
                                {#if model.warnings && model.warnings.length > 0}
                                    <tr class="border-b border-gray-100 dark:border-gray-700">
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
        </section>
    {/if}

    <section class="rounded-xl bg-white dark:bg-gray-800 border border-gray-200 dark:border-gray-700 p-5">
        <h3 class="text-base font-semibold text-gray-900 dark:text-gray-100">Run history</h3>
        {#if runs.length === 0}
            <p class="mt-2 text-sm text-gray-500 dark:text-gray-400">No runs yet.</p>
        {:else}
            <ul class="mt-2 divide-y divide-gray-200 dark:divide-gray-700">
                {#each runs as row (row.run_id)}
                    <li class="py-2 flex items-center justify-between text-sm">
                        <button
                            type="button"
                            onclick={() => { selectedRunId = row.run_id; refresh(); }}
                            class="text-left flex-1 hover:text-blue-600 dark:hover:text-blue-400"
                        >
                            <span class="font-mono">{row.run_id}</span>
                            <span class="ml-2 text-xs text-gray-500 dark:text-gray-400">
                                {#if row.duration_seconds}{Math.round(row.duration_seconds / 60)} min · {/if}
                                {row.model_count ?? 0} models · {row.total_species ?? 0} species
                                {#if row.region} · {row.region}{/if}
                                {#if row.error} · <span class="text-red-600 dark:text-red-400">error</span>{/if}
                            </span>
                        </button>
                        <button
                            type="button"
                            onclick={() => deleteRun(row.run_id)}
                            class="ml-4 text-xs text-gray-500 dark:text-gray-400 hover:text-red-600 dark:hover:text-red-400"
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
