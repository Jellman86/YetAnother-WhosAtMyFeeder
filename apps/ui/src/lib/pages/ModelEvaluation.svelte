<script lang="ts">
    import { onDestroy, onMount } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import Separator from '../components/Separator.svelte';
    import SettingsRow from '../components/settings/_primitives/SettingsRow.svelte';
    import SettingsToggle from '../components/settings/_primitives/SettingsToggle.svelte';
    import { fetchAvailableModels, fetchInstalledModels } from '../api/classifier';
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
    import { confirmAction } from '../stores/confirm_dialog.svelte';
    import { pageRefreshAction } from '../stores/page_refresh_action.svelte';
    import { identificationModelName } from '../settings/identification-models';
    import { formatDateTime } from '../utils/datetime';
    import { isCompatibilityOnlyRun, modelEvalScores } from '../utils/model-eval-scores';
    import {
        checkRowProblem,
        downloadStatement,
        evaluationFiles,
        evaluationProblem,
        evaluationProgress,
        evaluationStarted,
        historyPane,
        missingModelDownload,
        providerCheck,
        skipReason,
        stopCause,
        warningCopy,
        type DownloadEstimate,
        type EvaluationProblem,
        type ProviderCheck,
    } from '../utils/model-eval-view';

    // Where the server keeps each evaluation's files, shown beside the downloads.
    const RUNS_FOLDER = '/config/yawamf-eval';
    const DEVICE_MATRIX_FILE = 'device_matrix.json';
    const LISTED_EVALUATIONS = 20;

    type Tone = 'neutral' | 'pass' | 'attention' | 'failure';
    // A result is its word in ordinary ink. The dot beside it only helps the eye find the rows that
    // differ: amber where the owner should look, red only for a provider that really failed.
    const TONE_DOT: Record<Tone, string> = {
        neutral: 'bg-status-neutral',
        pass: 'bg-status-ok',
        attention: 'bg-status-attention',
        failure: 'bg-status-fail',
    };

    interface Cell { text: string | null; tone?: Tone; dot?: boolean }
    interface Note { tone: Tone; label: string; text: string }
    interface Row { id: string; name: string; technical: string | null; kind?: string; cells: Cell[]; notes: Note[] }
    interface Column { label: string; numeric?: boolean; nowrap?: boolean }
    interface ModelTable { columns: Column[]; rows: Row[] }

    type DownloadReading =
        | { status: 'idle' | 'reading' | 'unreadable' }
        | { status: 'read'; estimate: DownloadEstimate };

    let runs = $state.raw<ModelEvalRunRow[]>([]);
    let active = $state.raw<ModelEvalActiveStatus | null>(null);
    let historyLoaded = $state(false);
    let historyProblem = $state<EvaluationProblem | null>(null);
    let selectedRunId = $state<string | null>(null);
    let selectedRun = $state.raw<ModelEvalRunSummary | null>(null);
    let deviceMatrix = $state.raw<DeviceMatrix | null>(null);
    let resultsProblem = $state<EvaluationProblem | null>(null);
    let startProblem = $state<EvaluationProblem | null>(null);
    let actionProblem = $state<EvaluationProblem | null>(null);
    let starting = $state(false);
    let includePerImage = $state(false);
    let sweepDevices = $state(false);
    let optionsOpen = $state(false);
    let howOpen = $state(false);
    let download = $state<DownloadReading>({ status: 'idle' });
    let modelNames = $state.raw<ReadonlyMap<string, string>>(new Map());
    let downloadingFile = $state<string | null>(null);
    let pollHandle: number | null = null;
    let refreshInFlight = false;

    let pane = $derived(historyPane({ loaded: historyLoaded, failed: historyProblem !== null, count: runs.length }));
    let selectedIsRunning = $derived(selectedRunId !== null && selectedRunId === active?.run_id);
    let compatibilityOnly = $derived(isCompatibilityOnlyRun(selectedRun?.models));
    let files = $derived(evaluationFiles(selectedRun?.available_artifacts));
    let progress = $derived(active ? evaluationProgress(active) : null);

    let numberLocale = $derived($locale ?? undefined);
    let percentFormat = $derived(new Intl.NumberFormat(numberLocale, { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 }));
    let millisecondFormat = $derived(new Intl.NumberFormat(numberLocale, { style: 'unit', unit: 'millisecond', maximumFractionDigits: 0 }));

    function measured(value: number | null | undefined, format: Intl.NumberFormat): string | null {
        return value === null || value === undefined || Number.isNaN(value) ? null : format.format(value);
    }

    function downloadSize(megabytes: number): string {
        const inGigabytes = megabytes >= 1000;
        return new Intl.NumberFormat(numberLocale, {
            style: 'unit',
            unit: inGigabytes ? 'gigabyte' : 'megabyte',
            maximumFractionDigits: inGigabytes ? 1 : 0,
        }).format(inGigabytes ? megabytes / 1000 : megabytes);
    }

    function providerName(provider: string | null | undefined): string | null {
        if (!provider) return null;
        const labels: Record<string, string> = {
            cpu: $_('settings.detection.provider_cpu', { default: 'CPU (ONNX Runtime)' }),
            cuda: $_('settings.detection.provider_cuda', { default: 'NVIDIA CUDA' }),
            intel_gpu: $_('settings.detection.provider_intel_gpu', { default: 'Intel GPU (OpenVINO)' }),
            intel_cpu: $_('settings.detection.provider_intel_cpu', { default: 'Intel CPU (OpenVINO)' }),
            intel_npu: $_('settings.detection.provider_intel_npu', { default: 'Intel NPU (OpenVINO)' }),
        };
        return labels[provider] ?? provider;
    }

    function evaluationName(run: { run_id: string; started_at?: string | null }): string {
        const started = evaluationStarted(run);
        return started ? formatDateTime(started) : run.run_id;
    }

    function optionLabel(row: ModelEvalRunRow): string {
        const when = evaluationName(row);
        if (row.run_id === active?.run_id) return $_('model_eval.results.option_running', { values: { when }, default: '{when}, running now' });
        if (row.error_code) return $_('model_eval.results.option_stopped', { values: { when }, default: '{when}, stopped early' });
        return when;
    }

    type Severity = 'critical' | 'warning' | 'info';
    // A flagged model wants a look, not an alarm: amber for both, slate for a plain note.
    const SEVERITY_TONE: Record<Severity, Tone> = { critical: 'attention', warning: 'attention', info: 'neutral' };

    function severityOf(warning: ModelEvalWarning): Severity {
        return warning.severity === 'critical' || warning.severity === 'warning' ? warning.severity : 'info';
    }

    function warningNotes(model: ModelEvalModelSummary): Note[] {
        return (model.warnings ?? []).map((warning) => {
            const copy = warningCopy(model, warning);
            const severity = severityOf(warning);
            return {
                tone: SEVERITY_TONE[severity],
                label: $_(`model_eval.warning.severity.${severity}`),
                // The server's message is never the copy: every code, known or not, has a sentence here.
                text: $_(`model_eval.warning.${copy.key}`, { values: copy.values }),
            };
        });
    }

    const translate = (key: string, options?: { default?: string; values?: Record<string, string | number> }): string => $_(key, options);

    /** The names Settings › Models gives the model: what it is for, then its technical name. */
    function namesFor(modelId: string): { name: string; technical: string | null } {
        return identificationModelName({ id: modelId, name: modelNames.get(modelId) }, translate);
    }

    function modelRow(model: ModelEvalModelSummary, cells: Cell[]): Row {
        return { id: model.model_id, ...namesFor(model.model_id), cells, notes: warningNotes(model) };
    }

    let resultsTable = $derived.by((): ModelTable | null => {
        const models = selectedRun?.models ?? [];
        if (models.length === 0) return null;
        if (compatibilityOnly) {
            return {
                columns: [
                    { label: $_('model_eval.col_best_provider', { default: 'Fastest provider that passed' }), nowrap: true },
                    { label: $_('model_eval.col_median_inference', { default: 'Typical time per photo' }), numeric: true },
                    { label: $_('model_eval.col_validated_providers', { default: 'Providers that passed' }) },
                ],
                rows: models.map((model) => modelRow(model, [
                    { text: model.ready ? providerName(model.active_provider) : null },
                    // Every latency field of a compatibility row holds the best provider's median.
                    { text: measured(model.p50_latency_ms ?? model.mean_latency_ms, millisecondFormat) },
                    { text: model.validated_providers?.length ? model.validated_providers.map(providerName).join(', ') : null },
                ])),
            };
        }
        return {
            columns: [
                { label: $_('model_eval.results.col_first_guess', { default: 'First guess right' }), numeric: true },
                { label: $_('model_eval.results.col_top_three', { default: 'Right in top three' }), numeric: true },
                { label: $_('model_eval.results.col_common', { default: 'Common feeder birds' }), numeric: true },
                { label: $_('model_eval.results.col_local', { default: 'Birds near you' }), numeric: true },
                { label: $_('model_eval.results.col_can_name', { default: 'Species it can name' }), numeric: true },
                { label: $_('model_eval.results.col_average_time', { default: 'Average time' }), numeric: true },
                { label: $_('model_eval.results.col_slow_time', { default: 'Slow photos' }), numeric: true },
                { label: $_('model_eval.results.col_provider', { default: 'Ran on' }), nowrap: true },
            ],
            rows: models.map((model) => {
                const scores = modelEvalScores(model);
                return modelRow(model, [
                    { text: measured(scores.top1, percentFormat) },
                    { text: measured(scores.top3, percentFormat) },
                    { text: measured(scores.core, percentFormat) },
                    { text: measured(scores.region, percentFormat) },
                    { text: scores.canName ? $_('model_eval.results.can_name', { values: scores.canName, default: '{known} of {total}' }) : null },
                    { text: measured(model.mean_latency_ms, millisecondFormat) },
                    { text: measured(model.p95_latency_ms, millisecondFormat) },
                    { text: providerName(model.active_provider) },
                ]);
            }),
        };
    });

    function checkCell(check: ProviderCheck): Cell {
        switch (check.kind) {
            case 'not_tested':
                return { text: $_('model_eval.checks.cell.not_tested', { default: 'Not tested' }), dot: true };
            case 'did_not_load':
                return { text: $_('model_eval.checks.cell.did_not_load', { default: 'Did not load' }), tone: 'failure', dot: true };
            case 'unusable_output':
                return { text: $_('model_eval.checks.cell.unusable_output', { default: 'Unusable output' }), tone: 'failure', dot: true };
            case 'reference':
                return { dot: true, text: check.photos
                    ? $_('model_eval.checks.cell.reference', { values: { photos: check.photos } })
                    : $_('model_eval.checks.cell.reference_plain', { default: 'Reference' }) };
            case 'same':
                return { text: $_(check.boxes ? 'model_eval.checks.cell.same_boxes' : 'model_eval.checks.cell.same', { values: { photos: check.photos } }), tone: 'pass', dot: true };
            case 'differs':
                return { text: $_(check.boxes ? 'model_eval.checks.cell.differs_boxes' : 'model_eval.checks.cell.differs', { values: { same: check.same, photos: check.photos } }), tone: 'attention', dot: true };
            case 'ran':
                return { text: $_('model_eval.checks.cell.ran', { default: 'Ran' }), tone: 'pass', dot: true };
        }
    }

    // The accuracy columns, explained once under "How this works" whatever evaluation is shown.
    let columnMeanings = $derived([
        { label: $_('model_eval.results.col_first_guess', { default: 'First guess right' }), meaning: $_('model_eval.how.col.first_guess') },
        { label: $_('model_eval.results.col_top_three', { default: 'Right in top three' }), meaning: $_('model_eval.how.col.top_three') },
        { label: $_('model_eval.results.col_common', { default: 'Common feeder birds' }), meaning: $_('model_eval.how.col.common') },
        { label: $_('model_eval.results.col_local', { default: 'Birds near you' }), meaning: $_('model_eval.how.col.local') },
        { label: $_('model_eval.results.col_can_name', { default: 'Species it can name' }), meaning: $_('model_eval.how.col.can_name') },
        { label: $_('model_eval.results.col_average_time', { default: 'Average time' }), meaning: $_('model_eval.how.col.average_time') },
        { label: $_('model_eval.results.col_slow_time', { default: 'Slow photos' }), meaning: $_('model_eval.how.col.slow_time') },
        { label: $_('model_eval.results.col_provider', { default: 'Ran on' }), meaning: $_('model_eval.how.col.provider') },
    ]);

    let checksTable = $derived.by((): ModelTable | null => {
        if (!deviceMatrix) return null;
        const providers = deviceMatrix.providers?.length ? deviceMatrix.providers : deviceMatrix.devices;
        const entries = [...Object.entries(deviceMatrix.models), ...Object.entries(deviceMatrix.crop_detectors ?? {})];
        return {
            columns: providers.map((provider) => ({ label: providerName(provider) ?? provider })),
            rows: entries.map(([modelId, row]) => ({
                id: `${row.comparison_kind ?? 'classifier'}:${modelId}`,
                ...namesFor(modelId),
                kind: row.comparison_kind === 'crop_box' ? $_('model_eval.checks.finder', { default: 'Bird finder' }) : undefined,
                cells: providers.map((provider) => checkCell(providerCheck(row, provider))),
                // The row's own text may be what an exception said; only its code is read.
                notes: row.error
                    ? [{ tone: 'attention' as const, label: $_('model_eval.warning.severity.critical', { default: 'Needs a look' }), text: $_(`model_eval.checks.row.${checkRowProblem(row.error)}`) }]
                    : [],
            })),
        };
    });

    let skippedModels = $derived((selectedRun?.skipped_models ?? []).map((skipped) => ({
        id: skipped.model_id,
        ...namesFor(skipped.model_id),
        reason: $_(`model_eval.skipped.${skipReason(skipped.reason)}`),
    })));
    let stopped = $derived(stopCause(selectedRun?.error_code));

    let testSetFacts = $derived.by((): string[] => {
        const facts: string[] = [];
        const testSet = selectedRun?.test_set;
        if (testSet) {
            facts.push($_('model_eval.results.species', { values: { count: testSet.total_species } }));
            facts.push($_('model_eval.results.photos', { values: { count: testSet.total_images } }));
            if (testSet.region) facts.push($_('model_eval.results.region', { values: { region: testSet.region }, default: 'Region {region}' }));
        }
        const seconds = selectedRun?.duration_seconds;
        if (seconds) {
            const minutes = Math.round(seconds / 60);
            facts.push(minutes >= 1
                ? $_('model_eval.results.duration', { values: { minutes } })
                : $_('model_eval.results.under_a_minute', { default: 'Under a minute' }));
        }
        return facts;
    });

    // Only the newest selection may land: a slow reply for an evaluation the owner has since
    // moved away from must not replace the one they are looking at.
    let selectionRequest = 0;

    async function loadSelectedRun(runId: string): Promise<void> {
        const request = ++selectionRequest;
        const current = (): boolean => request === selectionRequest && runId === selectedRunId;
        try {
            const summary = await getModelEvalRun(runId);
            const matrix = summary.available_artifacts?.includes(DEVICE_MATRIX_FILE)
                ? await getModelEvalDeviceMatrix(runId)
                : null;
            if (!current()) return;
            selectedRun = summary;
            deviceMatrix = matrix;
            resultsProblem = null;
        } catch (cause) {
            if (current()) resultsProblem = evaluationProblem('results', cause);
        }
    }

    function selectRun(runId: string): void {
        if (runId !== selectedRunId) {
            selectedRun = null;
            deviceMatrix = null;
            resultsProblem = null;
            actionProblem = null;
        }
        selectedRunId = runId;
        void loadSelectedRun(runId);
    }

    async function refresh(reloadSelected = false): Promise<void> {
        if (refreshInFlight) return;
        refreshInFlight = true;
        try {
            const list = await listModelEvalRuns();
            const justFinished = active !== null && !list.active;
            runs = list.runs ?? [];
            active = list.active ?? null;
            historyLoaded = true;
            historyProblem = null;
            if (selectedRunId && !runs.some((row) => row.run_id === selectedRunId)) {
                selectedRunId = null;
                selectedRun = null;
                deviceMatrix = null;
                resultsProblem = null;
            }
            const firstSelection = !selectedRunId && runs.length > 0;
            if (firstSelection) selectedRunId = runs[0].run_id;
            // A finished evaluation does not change, so it is read once: only the running one,
            // or one that has just ended, is read again while the page polls.
            const stillChanging = selectedRunId === list.active?.run_id || justFinished;
            if (selectedRunId && (reloadSelected || firstSelection || stillChanging || selectedRun === null)) {
                await loadSelectedRun(selectedRunId);
            }
        } catch (cause) {
            historyProblem = evaluationProblem('history', cause);
        } finally {
            refreshInFlight = false;
        }
    }

    function startPolling(): void {
        if (pollHandle) return;
        pollHandle = window.setInterval(() => {
            if (!document.hidden) void refresh();
        }, 2000);
    }
    function stopPolling(): void {
        if (pollHandle) {
            clearInterval(pollHandle);
            pollHandle = null;
        }
    }

    $effect(() => {
        if (active) startPolling();
        else stopPolling();
    });

    $effect(() => pageRefreshAction.register(() => refresh(true)));

    async function readDownload(): Promise<void> {
        download = { status: 'reading' };
        try {
            const [registry, installed] = await Promise.all([fetchAvailableModels(), fetchInstalledModels()]);
            download = { status: 'read', estimate: missingModelDownload(registry, installed) };
        } catch {
            // The size is advice: without it the page says it could not be read, and still asks first.
            download = { status: 'unreadable' };
        }
    }

    function setSweepDevices(next: boolean): void {
        sweepDevices = next;
        if (next) void readDownload();
    }

    /** The sentence that states the download. A size is given only for the models that have one. */
    function downloadLine(reading: DownloadReading): string {
        if (reading.status === 'unreadable') return $_('model_eval.start.download_unknown');
        if (reading.status !== 'read') return $_('model_eval.start.download_reading', { default: 'Reading how much would be downloaded…' });
        const { count, megabytes, unknownSizes } = reading.estimate;
        switch (downloadStatement(reading.estimate)) {
            case 'nothing':
                return $_('model_eval.start.download_none', { default: 'Every model is already installed, so nothing is downloaded.' });
            case 'sized':
                return $_('model_eval.start.download_size', { values: { count, size: downloadSize(megabytes) } });
            case 'partly_sized':
                return $_('model_eval.start.download_size_partial', { values: { count, unknown: unknownSizes, size: downloadSize(megabytes) } });
            case 'unsized':
                return $_('model_eval.start.download_size_unknown', { values: { count } });
        }
    }

    let nothingToDownload = $derived(download.status === 'read' && download.estimate.count === 0);

    /** Checking every model downloads the missing ones first, so the owner agrees to what that is. */
    async function agreeToDownload(): Promise<boolean> {
        if (download.status === 'reading' || download.status === 'idle') await readDownload();
        if (nothingToDownload) return true;
        return confirmAction({
            title: download.status === 'read'
                ? $_('model_eval.confirm_download.title', { values: { count: download.estimate.count } })
                : $_('model_eval.confirm_download.title_unknown', { default: 'Download the missing models?' }),
            message: `${downloadLine(download)} ${$_('model_eval.start.download_note')}`,
            confirmLabel: $_('model_eval.confirm_download.confirm', { default: 'Download and start' }),
            cancelLabel: $_('model_eval.confirm_download.cancel', { default: 'Go back' }),
            tone: 'default',
        });
    }

    async function startRun(): Promise<void> {
        if (sweepDevices && !(await agreeToDownload())) return;
        starting = true;
        startProblem = null;
        try {
            const { run_id } = await startModelEvalRun({ include_per_image: includePerImage, sweep_devices: sweepDevices });
            selectedRunId = run_id;
            selectedRun = null;
            deviceMatrix = null;
            resultsProblem = null;
            await refresh(true);
            startPolling();
        } catch (cause) {
            startProblem = evaluationProblem('start', cause);
        } finally {
            starting = false;
        }
    }

    async function stopRun(): Promise<void> {
        if (!active) return;
        const runId = active.run_id;
        const confirmed = await confirmAction({
            title: $_('model_eval.confirm_stop.title', { default: 'Stop the evaluation?' }),
            message: $_('model_eval.confirm_stop.message'),
            confirmLabel: $_('model_eval.confirm_stop.confirm', { default: 'Stop evaluation' }),
            cancelLabel: $_('model_eval.confirm_stop.cancel', { default: 'Keep running' }),
        });
        if (!confirmed) return;
        startProblem = null;
        try {
            await cancelModelEvalRun(runId);
            await refresh(true);
        } catch (cause) {
            startProblem = evaluationProblem('stop', cause);
        }
    }

    async function deleteSelected(): Promise<void> {
        const row = runs.find((candidate) => candidate.run_id === selectedRunId);
        if (!row) return;
        const confirmed = await confirmAction({
            title: $_('model_eval.confirm_delete.title', { default: 'Delete this evaluation?' }),
            message: $_('model_eval.confirm_delete.message', { values: { when: evaluationName(row) } }),
            confirmLabel: $_('model_eval.confirm_delete.confirm', { default: 'Delete evaluation' }),
        });
        if (!confirmed) return;
        actionProblem = null;
        try {
            await deleteModelEvalRun(row.run_id);
            if (selectedRunId === row.run_id) {
                selectedRunId = null;
                selectedRun = null;
                deviceMatrix = null;
            }
            await refresh();
        } catch (cause) {
            actionProblem = evaluationProblem('delete', cause);
        }
    }

    async function downloadFile(runId: string, file: string): Promise<void> {
        if (downloadingFile) return;
        downloadingFile = file;
        actionProblem = null;
        try {
            const blob = await fetchModelEvalArtifact(runId, file);
            const url = URL.createObjectURL(blob);
            const link = document.createElement('a');
            link.href = url;
            link.download = file;
            document.body.appendChild(link);
            try {
                link.click();
            } finally {
                link.remove();
                URL.revokeObjectURL(url);
            }
        } catch (cause) {
            actionProblem = evaluationProblem('download', cause);
        } finally {
            downloadingFile = null;
        }
    }

    onMount(() => {
        void refresh();
        // The registry gives each model its catalogue name; without it a row keeps its identifier.
        fetchAvailableModels()
            .then((registry) => { modelNames = new Map(registry.map((model) => [model.id, model.name])); })
            .catch(() => { modelNames = new Map(); });
    });
    onDestroy(stopPolling);
</script>

{#snippet problem(issue: EvaluationProblem, retry?: () => void)}
    <div role="alert" class="flex flex-col gap-3 rounded-xl border border-status-fail-line bg-status-fail-soft p-3 text-sm text-status-fail sm:flex-row sm:items-center sm:justify-between" data-model-eval-problem>
        <div class="min-w-0 space-y-1">
            <p class="font-semibold">{$_(`model_eval.problem.what.${issue.what}`)}</p>
            <p>{$_(`model_eval.problem.cause.${issue.cause}`)}</p>
        </div>
        {#if retry}
            <button type="button" class="btn btn-secondary shrink-0" onclick={retry}>{$_('error.try_again', { default: 'Try again' })}</button>
        {/if}
    </div>
{/snippet}

{#snippet placeholder(label: string)}
    <div class="space-y-3" role="status" aria-label={label} data-model-eval-placeholder>
        <div class="h-11 max-w-sm animate-pulse rounded-xl bg-surface-raised motion-reduce:animate-none"></div>
        <div class="h-40 animate-pulse rounded-xl bg-surface-raised motion-reduce:animate-none"></div>
    </div>
{/snippet}

{#snippet modelName(row: Row)}
    <span class="block">{row.name}</span>
    {#if row.technical}
        <span class="block text-xs font-normal text-muted" data-model-technical-name>{row.technical}</span>
    {/if}
    {#if row.kind}
        <span class="block text-xs font-normal text-muted">{row.kind}</span>
    {/if}
{/snippet}

{#snippet cellValue(cell: Cell)}
    {#if cell.text === null}
        <span aria-hidden="true">—</span><span class="sr-only">{$_('model_eval.results.not_measured', { default: 'Not measured' })}</span>
    {:else if cell.dot}
        <span class="inline-flex items-baseline gap-2">
            <span class="inline-block h-1.5 w-1.5 shrink-0 -translate-y-0.5 rounded-full {TONE_DOT[cell.tone ?? 'neutral']}" aria-hidden="true"></span>
            <span>{cell.text}</span>
        </span>
    {:else}
        {cell.text}
    {/if}
{/snippet}

<!-- Every note reads the same: a dot, what kind of note it is, and one quiet sentence with the next step. -->
{#snippet noteLines(notes: Note[])}
    <ul class="space-y-1 text-sm text-muted">
        {#each notes as note}
            <li class="flex items-baseline gap-2">
                <span class="inline-block h-1.5 w-1.5 shrink-0 -translate-y-0.5 rounded-full {TONE_DOT[note.tone]}" aria-hidden="true"></span>
                <span class="min-w-0"><span class="font-semibold text-strong">{note.label}</span> {note.text}</span>
            </li>
        {/each}
    </ul>
{/snippet}

<!-- A plain text disclosure: its words say what opens and the chevron says whether it is open. -->
{#snippet disclosure(label: string, open: boolean, controls: string, toggle: () => void)}
    <button type="button" class="btn btn-ghost -ml-2 justify-start px-2 text-left" aria-expanded={open} aria-controls={controls} onclick={toggle}>
        <span class="min-w-0 wrap-break-word">{label}</span>
        <svg class="h-4 w-4 shrink-0 transition-transform motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
    </button>
{/snippet}

<!-- One set of rows, laid out twice by the panel's own width: a table where the columns fit, and a
     list of labelled figures where they do not, so a phone never scrolls a table sideways. -->
{#snippet modelTable(table: ModelTable, labelId: string)}
    <!-- A table that can scroll sideways at enlarged text takes a tab stop, so the keyboard can scroll it (WCAG 2.1.1).
         A group, not a region: its panel is already the landmark of that name. -->
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <div class="hidden overflow-x-auto focus-ring @2xl:block" role="group" tabindex="0" aria-labelledby={labelId}>
        <table class="w-full text-sm">
            <thead>
                <tr class="border-b border-line-soft text-left align-bottom text-xs font-semibold text-muted">
                    <th scope="col" class="py-2 pr-4">{$_('model_eval.col_model', { default: 'Model' })}</th>
                    {#each table.columns as column}
                        <th scope="col" class="px-2 py-2 {column.numeric ? 'text-right' : ''}">{column.label}</th>
                    {/each}
                </tr>
            </thead>
            <tbody>
                {#each table.rows as row (row.id)}
                    <tr class="align-top {row.notes.length ? '' : 'border-b border-line-soft'}">
                        <th scope="row" class="whitespace-nowrap py-2 pr-4 text-left font-semibold text-strong">{@render modelName(row)}</th>
                        {#each row.cells as cell, index}
                            <td class="px-2 py-2 {table.columns[index].numeric ? 'whitespace-nowrap text-right tabular-nums' : ''} {table.columns[index].nowrap ? 'whitespace-nowrap' : ''} text-ink">{@render cellValue(cell)}</td>
                        {/each}
                    </tr>
                    {#if row.notes.length}
                        <tr class="border-b border-line-soft">
                            <td colspan={table.columns.length + 1} class="pb-3">{@render noteLines(row.notes)}</td>
                        </tr>
                    {/if}
                {/each}
            </tbody>
        </table>
    </div>
    <ul class="divide-y divide-line-soft border-y border-line-soft @2xl:hidden" aria-labelledby={labelId}>
        {#each table.rows as row (row.id)}
            <li class="space-y-2 py-3">
                <h3 class="text-sm font-semibold text-strong wrap-break-word">{@render modelName(row)}</h3>
                <dl class="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                    {#each table.columns as column, index}
                        <dt class="text-muted">{column.label}</dt>
                        <dd class="flex justify-end text-right tabular-nums text-ink">{@render cellValue(row.cells[index])}</dd>
                    {/each}
                </dl>
                {#if row.notes.length}{@render noteLines(row.notes)}{/if}
            </li>
        {/each}
    </ul>
{/snippet}

<!-- A screen tall, so the footer does not sit under a short page and move when the results land. -->
<div class="min-h-screen space-y-6" data-model-evaluation>
    <!-- Where the card is wide enough (about 1440 px of window) what the evaluation is and its options
         stand on the left at a reading measure, and the action and its progress beside them, rather
         than one strip with the rest of the card empty. -->
    <section class="card-base @container p-5" aria-labelledby="model-eval-start-title">
        <div class="@5xl:grid @5xl:grid-cols-12 @5xl:gap-x-10">
            <div class="min-w-0 @5xl:col-span-7" data-model-eval-start-about>
                <h2 id="model-eval-start-title" class="font-display text-lg font-semibold text-strong">
                    {$_('model_eval.start.title', { default: 'Start an evaluation' })}
                </h2>
                <p class="mt-2 max-w-prose text-sm leading-relaxed text-muted">{$_('model_eval.start.what')}</p>

                <div class="mt-2 max-w-prose">
                    {@render disclosure($_('model_eval.how.title', { default: 'How this works' }), howOpen, 'model-eval-how', () => (howOpen = !howOpen))}
                    {#if howOpen}
                        <div id="model-eval-how" class="space-y-3 pb-2 text-sm leading-relaxed text-muted">
                            <p>{$_('model_eval.how.photos')}</p>
                            <p>{$_('model_eval.how.cost')}</p>
                            <p>{$_('model_eval.how.limit')}</p>
                            <div>
                                <h3 class="text-sm font-semibold text-strong">{$_('model_eval.how.columns_title', { default: 'What the columns mean' })}</h3>
                                <dl class="mt-1 space-y-1">
                                    {#each columnMeanings as column}
                                        <div class="flex flex-wrap gap-x-2">
                                            <dt class="font-semibold text-strong">{column.label}</dt>
                                            <dd class="min-w-0 flex-1 basis-64">{column.meaning}</dd>
                                        </div>
                                    {/each}
                                </dl>
                            </div>
                            <p>{$_('model_eval.how.checks')}</p>
                        </div>
                    {/if}
                </div>

                <div class="max-w-prose">
                    {@render disclosure(
                        optionsOpen
                            ? $_('model_eval.start.options_hide', { default: 'Hide evaluation options' })
                            : $_('model_eval.start.options_show', { default: 'Show evaluation options' }),
                        optionsOpen,
                        'model-eval-options',
                        () => (optionsOpen = !optionsOpen)
                    )}
                    {#if optionsOpen}
                        <div id="model-eval-options" class="space-y-4 pb-2 pt-1">
                        <SettingsRow
                            labelId="model-eval-each-photo"
                            label={$_('model_eval.start.each_photo_label', { default: 'Keep each photo’s result' })}
                            description={$_('model_eval.start.each_photo_desc')}
                        >
                            <SettingsToggle
                                checked={includePerImage}
                                labelledBy="model-eval-each-photo"
                                srLabel={$_('model_eval.start.each_photo_label', { default: 'Keep each photo’s result' })}
                                disabled={active !== null || starting}
                                onchange={(next) => (includePerImage = next)}
                            />
                        </SettingsRow>
                        <SettingsRow
                            labelId="model-eval-all-models"
                            label={$_('model_eval.start.all_models_label', { default: 'Check every model on every provider' })}
                            description={$_('model_eval.start.all_models_desc')}
                        >
                            <SettingsToggle
                                checked={sweepDevices}
                                labelledBy="model-eval-all-models"
                                srLabel={$_('model_eval.start.all_models_label', { default: 'Check every model on every provider' })}
                                disabled={active !== null || starting}
                                onchange={setSweepDevices}
                            />
                        </SettingsRow>
                        {#if sweepDevices}
                            <div class="space-y-1 text-sm text-ink" role="status" data-model-eval-download>
                                <p class="font-semibold">{downloadLine(download)}</p>
                                {#if !nothingToDownload && download.status !== 'reading'}
                                    <p class="text-muted">{$_('model_eval.start.download_note')}</p>
                                {/if}
                            </div>
                        {/if}
                        </div>
                    {/if}
                </div>
            </div>

            <div class="min-w-0 @5xl:col-span-5" data-model-eval-start-action>
                <div class="mt-4 flex flex-wrap items-center gap-3 @5xl:mt-0">
                    <button
                        type="button"
                        class="btn btn-primary"
                        disabled={active !== null || starting}
                        aria-describedby={active ? 'model-eval-running-reason' : undefined}
                        onclick={startRun}
                    >
                        {active
                            ? $_('model_eval.start.running', { default: 'Evaluation running' })
                            : $_('model_eval.start.action', { default: 'Start evaluation' })}
                    </button>
                    {#if active}
                        <button type="button" class="btn btn-danger" onclick={stopRun}>
                            {$_('model_eval.start.stop', { default: 'Stop evaluation' })}
                        </button>
                    {/if}
                </div>
                {#if active}
                    <p id="model-eval-running-reason" class="mt-2 text-sm text-muted">
                        {$_('model_eval.start.running_reason', { default: 'One evaluation runs at a time. Stop this one to start another.' })}
                    </p>
                {/if}

                {#if startProblem}
                    <div class="mt-4">{@render problem(startProblem)}</div>
                {/if}

                {#if progress}
                    <div class="mt-4 max-w-3xl space-y-2" data-model-eval-progress>
                        <div class="flex flex-wrap justify-between gap-x-4 text-sm font-medium text-ink">
                            <span role="status">{$_(`model_eval.progress.phase.${progress.phase}`)}</span>
                            {#if progress.total > 0}
                                <span class="tabular-nums">{$_('model_eval.progress.count', { values: { done: progress.done, total: progress.total }, default: '{done} of {total}' })}</span>
                            {/if}
                        </div>
                        <div
                            role="progressbar"
                            aria-label={$_('model_eval.progress.label', { default: 'Progress of the evaluation' })}
                            aria-valuemin="0"
                            aria-valuemax="100"
                            aria-valuenow={progress.percent ?? undefined}
                            class="h-2 w-full overflow-hidden rounded-full bg-track"
                        >
                            {#if progress.percent === null}
                                <div class="h-full w-full animate-pulse rounded-full bg-accent/50 motion-reduce:animate-none"></div>
                            {:else}
                                <div class="h-full rounded-full bg-accent transition-all duration-500 motion-reduce:transition-none" style="width: {progress.percent}%"></div>
                            {/if}
                        </div>
                    </div>
                {/if}
            </div>
        </div>
    </section>

    <section class="card-base @container p-5" aria-labelledby="model-eval-results-title" aria-busy={pane === 'loading'}>
        <!-- The header keeps a control's height from the start, so nothing moves when Delete arrives. -->
        <div class="flex min-h-11 flex-wrap items-center justify-between gap-x-4 gap-y-2">
            <h2 id="model-eval-results-title" class="font-display text-lg font-semibold text-strong">
                {$_('model_eval.results.title', { default: 'Results' })}
            </h2>
            {#if pane === 'list'}
                <button
                    type="button"
                    class="btn btn-ghost -mr-2 text-status-fail"
                    disabled={selectedIsRunning}
                    aria-describedby={selectedIsRunning ? 'model-eval-delete-blocked' : undefined}
                    onclick={deleteSelected}
                >
                    {$_('model_eval.results.delete', { default: 'Delete this evaluation' })}
                </button>
            {/if}
        </div>

        <div class="mt-2 space-y-4">
            {#if historyProblem}
                {@render problem(historyProblem, () => void refresh(true))}
                {#if pane === 'list'}
                    <p class="text-sm text-muted">{$_('model_eval.problem.stale', { default: 'What is shown below may be out of date.' })}</p>
                {/if}
            {/if}

            {#if pane === 'loading'}
                {@render placeholder($_('model_eval.results.loading_list', { default: 'Reading the past evaluations' }))}
            {:else if pane === 'empty'}
                <p class="max-w-prose text-sm text-muted" data-model-eval-empty>
                    {$_('model_eval.results.empty', { default: 'No evaluation has been run yet. Start one above and its results appear here.' })}
                </p>
            {:else if pane !== 'failed'}
                    <div class="space-y-1.5 sm:max-w-sm">
                        <label for="model-eval-choose" class="block text-sm font-semibold text-strong">{$_('model_eval.results.choose', { default: 'Evaluation' })}</label>
                        <select
                            id="model-eval-choose"
                            class="select-base min-h-11"
                            value={selectedRunId}
                            onchange={(event) => selectRun(event.currentTarget.value)}
                        >
                            {#each runs as row (row.run_id)}
                                <option value={row.run_id}>{optionLabel(row)}</option>
                            {/each}
                        </select>
                    </div>
                {#if selectedIsRunning}
                    <p id="model-eval-delete-blocked" class="text-sm text-muted">
                        {$_('model_eval.results.delete_blocked', { default: 'Stop it before you delete it.' })}
                    </p>
                {/if}
                {#if runs.length >= LISTED_EVALUATIONS}
                    <p class="text-sm text-muted">{$_('model_eval.results.capped', { default: 'Only the 20 most recent evaluations are listed.' })}</p>
                {/if}

                {#if actionProblem}
                    {@render problem(actionProblem)}
                {/if}

                {#if resultsProblem}
                    {@render problem(resultsProblem, () => selectedRunId && selectRun(selectedRunId))}
                {:else if !selectedRun}
                    {@render placeholder($_('model_eval.results.loading', { default: 'Reading the results' }))}
                {:else}
                    {#if testSetFacts.length}
                        <p class="text-sm text-muted" data-model-eval-facts>
                            {#each testSetFacts as fact, index}{#if index > 0}<Separator spaced />{/if}<span class="whitespace-nowrap">{fact}</span>{/each}
                        </p>
                    {/if}

                    {#if selectedRun.in_progress || selectedIsRunning}
                        <p class="text-sm text-ink" data-model-eval-still-running>
                            {$_('model_eval.results.still_running', { default: 'This evaluation is still running. Results appear here as each model finishes.' })}
                        </p>
                    {/if}

                    {#if stopped}
                        <div class="flex items-baseline gap-2 text-sm text-muted" data-model-eval-stopped>
                            <span class="inline-block h-1.5 w-1.5 shrink-0 -translate-y-0.5 rounded-full {TONE_DOT.attention}" aria-hidden="true"></span>
                            <p class="min-w-0 max-w-prose"><span class="font-semibold text-strong">{$_('model_eval.results.stopped_early')}</span> {$_(`model_eval.stopped.${stopped}`)}</p>
                        </div>
                    {/if}

                    {#if compatibilityOnly}
                        <div class="rounded-xl bg-surface-raised p-3">
                            <h3 class="text-sm font-semibold text-strong">
                                {$_('model_eval.compat_only_title', { default: 'Provider check only' })}
                            </h3>
                            <p class="mt-1 max-w-prose text-sm text-muted">
                                {$_('model_eval.compat_only_body')}
                            </p>
                        </div>
                    {/if}

                    {#if resultsTable}
                        {@render modelTable(resultsTable, 'model-eval-results-title')}
                        {#if !compatibilityOnly}
                            <p class="max-w-prose text-sm text-muted">
                                {#if selectedRun.models?.some((model) => model.vocabulary_known)}{$_('model_eval.results.vocabulary_note')}{' '}{/if}{$_('model_eval.results.columns_hint')}
                            </p>
                        {/if}
                    {:else if !selectedRun.in_progress && !selectedIsRunning && !stopped && skippedModels.length === 0}
                        <p class="text-sm text-muted">{$_('model_eval.results.no_models', { default: 'No model was tested in this evaluation.' })}</p>
                    {/if}

                    {#if skippedModels.length}
                        <div data-model-eval-skipped>
                            <h3 class="text-sm font-semibold text-strong">{$_('model_eval.skipped.title', { default: 'Models that were not tested' })}</h3>
                            <ul class="mt-2 space-y-2 text-sm">
                                {#each skippedModels as skipped (skipped.id)}
                                    <li class="flex gap-2">
                                        <span class="mt-2 inline-block h-1.5 w-1.5 shrink-0 rounded-full {TONE_DOT.attention}" aria-hidden="true"></span>
                                        <span class="min-w-0 text-ink">
                                            <span class="block font-semibold text-strong">{skipped.name}</span>
                                            {#if skipped.technical}
                                                <span class="block text-xs text-muted" data-model-technical-name>{skipped.technical}</span>
                                            {/if}
                                            <span class="block">{skipped.reason}</span>
                                        </span>
                                    </li>
                                {/each}
                            </ul>
                        </div>
                    {/if}

                    {#if files.length}
                        <div class="border-t border-line-soft pt-4" aria-busy={downloadingFile !== null}>
                            <p id="model-eval-files-title" class="eyebrow">{$_('model_eval.results.files', { default: 'Download the results' })}</p>
                            <!-- A secondary task: quiet text actions on one line, each still a full touch target. -->
                            <div class="-ml-2 flex flex-wrap items-center gap-x-1" role="group" aria-labelledby="model-eval-files-title">
                                {#each files as file, index (file.name)}
                                    {@const label = $_(`model_eval.results.file.${file.label}`)}
                                    <!-- Where the row wraps, a separator would be left hanging at a line end. -->
                                    {#if index > 0}<span class="hidden text-muted @2xl:inline"><Separator /></span>{/if}
                                    <button
                                        type="button"
                                        class="btn btn-ghost px-2 font-medium text-accent-ink hover:underline"
                                        disabled={downloadingFile !== null}
                                        aria-label={$_('model_eval.results.file_download', { values: { label, file: file.name }, default: 'Download {label} ({file})' })}
                                        onclick={() => selectedRun && downloadFile(selectedRun.run_id, file.name)}
                                    >
                                        {#if downloadingFile === file.name}
                                            <span class="h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent motion-reduce:animate-none" aria-hidden="true"></span>
                                        {:else}
                                            <svg class="h-4 w-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 4v11m0 0 4-4m-4 4-4-4M5 19h14" /></svg>
                                        {/if}
                                        {label}
                                    </button>
                                {/each}
                            </div>
                            <p class="text-xs text-muted">
                                {$_('model_eval.results.folder', { default: 'Folder on the server:' })}
                                <code class="font-mono wrap-break-word">{RUNS_FOLDER}/{selectedRun.run_id}/</code>
                            </p>
                        </div>
                    {/if}
                {/if}
            {/if}
        </div>
    </section>

    {#if checksTable}
        <section class="card-base @container p-5" aria-labelledby="model-eval-checks-title">
            <h2 id="model-eval-checks-title" class="font-display text-lg font-semibold text-strong">
                {$_('model_eval.checks.title', { default: 'Provider checks' })}
            </h2>
            <p class="mt-2 max-w-prose text-sm leading-relaxed text-muted">{$_('model_eval.checks.body')}</p>
            <div class="mt-4">{@render modelTable(checksTable, 'model-eval-checks-title')}</div>
        </section>
    {/if}
</div>
