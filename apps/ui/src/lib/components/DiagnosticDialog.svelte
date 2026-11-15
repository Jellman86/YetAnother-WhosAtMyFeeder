<script lang="ts">
    import DialogCloseButton from './DialogCloseButton.svelte';
    import type { Snippet } from 'svelte';
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { trapFocus } from '../utils/focus-trap';
    import { portal } from '../utils/portal';
    import { diagnosticHeadline, type DiagnosticStage, type DiagnosticStageState, type DiagnosticResult } from '../utils/diagnostic-runner';

    interface Props {
        title: string;
        subtitle?: string;
        // Optional small label above the title, for a caller with context the title lacks.
        eyebrow?: string;
        // The ordered checks. Callers own the truth: a stage only becomes
        // `passed`/`failed` when its check actually resolved that way.
        stages: DiagnosticStage[];
        // True while the underlying test is in flight.
        busy?: boolean;
        // Populated once the test finishes (success or failure).
        result?: DiagnosticResult | null;
        // Explanatory footnote shown under the checklist (e.g. what the probe sends).
        note?: string;
        // Optional meta strip snippet (e.g. "Provider · Model").
        summary?: Snippet;
        // Bumped by the caller on every run so the reveal animation restarts.
        runId?: number;
        retryLabel?: string;
        runningLabel?: string;
        closeLabel?: string;
        onClose: () => void;
        onRetry?: () => void;
    }

    let {
        title,
        subtitle,
        eyebrow,
        stages,
        busy = false,
        result = null,
        note,
        summary,
        runId = 0,
        retryLabel,
        runningLabel,
        closeLabel,
        onClose,
        onRetry
    }: Props = $props();

    let modalElement = $state<HTMLElement | null>(null);

    // Auto-progress: results may arrive from the backend all at once, but we
    // reveal them one check at a time so the dialog visibly steps forward like
    // the guided setup. This never fabricates a pass — a stage still shows its
    // real state; the reveal only controls *when* a resolved stage appears.
    let tick = $state(0);
    // Only *terminal* stages count as resolved. A stage that is still `running`
    // must not advance the reveal, or the dialog would force the next stage to
    // "running" while the current one (e.g. a live download) is still in flight.
    const resolvedCount = $derived(
        stages.filter((s) => s.state === 'passed' || s.state === 'failed' || s.state === 'warning' || s.state === 'skipped').length
    );
    const revealed = $derived(Math.min(resolvedCount, tick));

    $effect(() => {
        // Restart the reveal whenever a new run begins.
        void runId;
        tick = 0;
        const timer = setInterval(() => {
            tick += 1;
            // The run is over and every row is on show; ticking on would only wake the page.
            if (!busy && tick >= stages.length) clearInterval(timer);
        }, 350);
        return () => clearInterval(timer);
    });

    // What the user sees for each row: resolved rows appear in reveal order; the
    // next unrevealed row pulses while the test is still working; everything
    // beyond that waits.
    const displayStages = $derived(
        stages.map((stage, index): DiagnosticStage => {
            if (index < revealed) return stage;
            if (index === revealed && busy) return { ...stage, state: 'running' };
            return { ...stage, state: 'pending' };
        })
    );

    const completed = $derived(
        displayStages.filter(
            (s) => s.state === 'passed' || s.state === 'failed' || s.state === 'warning' || s.state === 'skipped'
        ).length
    );
    const progress = $derived(stages.length === 0 ? 0 : Math.round((completed / stages.length) * 100));
    const resultShown = $derived(Boolean(result) && revealed >= resolvedCount);

    // The one line assistive tech hears: the step in progress, then the outcome. The checklist
    // re-renders on every reveal tick, so announcing the whole body repeated it each time.
    const statusText = $derived.by(() => {
        if (result && resultShown) return [result.message, result.hint].filter(Boolean).join(' ');
        const runningIndex = displayStages.findIndex((stage) => stage.state === 'running');
        if (runningIndex < 0) return '';
        return $_('common.diagnostic_step_status', {
            values: { step: runningIndex + 1, total: stages.length, label: stages[runningIndex].label },
            default: 'Step {step} of {total}: {label}'
        });
    });

    onMount(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        // trapFocus returns focus to the opener on release; a second restore here would
        // override a deliberate move to another control.
        const releaseFocus = modalElement ? trapFocus(modalElement) : () => {};
        return () => {
            releaseFocus();
            document.body.style.overflow = previousOverflow;
        };
    });

    // The rows already state each outcome. A summary earns its place only when it says something
    // they do not: that everything passed, a message of its own, or a hint about what to do next.
    const summaryAddsSomething = $derived.by(() => {
        if (!result) return false;
        if (result.ok || result.hint) return true;
        const said = result.message.trim();
        const perStageCount = diagnosticHeadline(result, displayStages) !== result.message;
        const repeatsFailures = stages.filter((stage) => stage.state === 'failed').every((stage) => said.includes(stage.label));
        return !perStageCount && !repeatsFailures;
    });

    function stateWord(state: DiagnosticStageState): string {
        if (state === 'passed') return $_('common.diagnostic_state_passed', { default: 'Passed' });
        if (state === 'failed') return $_('common.diagnostic_state_failed', { default: 'Failed' });
        if (state === 'warning') return $_('common.diagnostic_state_warning', { default: 'Passed with a warning' });
        if (state === 'skipped') return $_('common.diagnostic_state_skipped', { default: 'Not run' });
        return '';
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape') onClose();
    }

    function stageIcon(state: DiagnosticStageState): string {
        if (state === 'passed') return '✓';
        if (state === 'failed') return '!';
        if (state === 'warning') return '!';
        if (state === 'skipped') return '–';
        return '';
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<div
    use:portal
    class="fixed inset-0 z-80 flex items-center justify-center overflow-y-auto bg-slate-950/60 p-4 backdrop-blur-xs"
    role="presentation"
>
    <div
        bind:this={modalElement}
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnostic-title"
        aria-describedby={subtitle ? 'diagnostic-description' : undefined}
        tabindex="-1"
        class="my-8 w-full max-w-2xl overflow-hidden rounded-2xl border border-white/10 bg-surface shadow-2xl ring-1 ring-black/5"
    >
        <!-- Plain divisions, not header and footer: the dialog is portalled to the body, where those
             elements would count as a second page banner and a second page footer. -->
        <div class="space-y-4 bg-surface-raised px-6 py-5">
            <div class="flex items-start justify-between gap-4">
                <div class="space-y-1">
                    {#if eyebrow}
                        <p class="text-xs font-semibold text-brand-700 dark:text-brand-300">{eyebrow}</p>
                    {/if}
                    <h2 id="diagnostic-title" class="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
                        {title}
                    </h2>
                    {#if subtitle}
                        <p id="diagnostic-description" class="text-sm text-slate-600 dark:text-slate-300">{subtitle}</p>
                    {/if}
                </div>
                <DialogCloseButton label={closeLabel} onclick={onClose} />
            </div>

            <div class="flex items-center gap-1.5" aria-hidden="true">
                {#each displayStages as stage}
                    <span class="h-1.5 flex-1 rounded-full transition-colors duration-300 {stage.state === 'passed' ? 'bg-brand-500' : stage.state === 'failed' ? 'bg-red-500' : stage.state === 'warning' ? 'bg-attention-500' : stage.state === 'running' ? 'animate-pulse bg-brand-400' : 'bg-slate-200 dark:bg-slate-700'}"></span>
                {/each}
            </div>
            <span class="sr-only" role="progressbar" aria-labelledby="diagnostic-title" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100">{progress}%</span>
        </div>

        <p class="sr-only" role="status">{statusText}</p>

        <div class="max-h-[68vh] space-y-4 overflow-y-auto p-6">
            {#if summary}
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
                    {@render summary()}
                </div>
            {/if}

            <ol class="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
                {#each displayStages as stage, index}
                    <li class="flex items-start gap-3 p-3.5 {stage.state === 'failed' ? 'bg-red-50/70 dark:bg-red-950/20' : stage.state === 'warning' ? 'bg-attention-50/70 dark:bg-attention-950/20' : stage.state === 'running' ? 'bg-brand-50/60 dark:bg-brand-950/15' : ''}">
                        <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-bold {stage.state === 'failed' ? 'bg-red-600 text-white' : stage.state === 'warning' ? 'bg-attention-500 text-white' : stage.state === 'passed' ? 'bg-success-600 text-white' : stage.state === 'running' ? 'animate-pulse bg-brand-700 text-white' : 'bg-slate-200 text-slate-600 dark:bg-slate-700 dark:text-slate-300'}">
                            {stageIcon(stage.state) || index + 1}
                        </span>
                        <div class="min-w-0 flex-1 space-y-0.5">
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="text-sm font-bold text-slate-900 dark:text-white">{stage.label}</h3>
                                {#if stage.state === 'running'}
                                    <span class="text-3xs font-bold text-brand-700 dark:text-brand-300">{runningLabel ?? $_('common.testing', { default: 'Testing' })}</span>
                                {:else if stateWord(stage.state)}
                                    <span class="text-xs font-semibold {stage.state === 'failed' ? 'text-red-700 dark:text-red-300' : 'text-slate-600 dark:text-slate-300'}" data-diagnostic-stage-state={stage.state}>{stateWord(stage.state)}</span>
                                {/if}
                            </div>
                            {#if stage.state !== 'pending'}
                                <p class="text-xs leading-relaxed text-slate-600 dark:text-slate-300">{stage.message}</p>
                            {/if}
                        </div>
                    </li>
                {/each}
            </ol>

            {#if result && resultShown && summaryAddsSomething}
                <div data-diagnostic-result class="rounded-2xl border p-4 {result.ok ? 'border-success-200 bg-success-50 text-success-900 dark:border-success-900/60 dark:bg-success-950/20 dark:text-success-100' : 'border-red-200 bg-red-50 text-red-900 dark:border-red-900/60 dark:bg-red-950/20 dark:text-red-100'}">
                    <p class="font-bold">{diagnosticHeadline(result, displayStages)}</p>
                    {#if result.hint}
                        <p class="mt-1 text-sm">{result.hint}</p>
                    {/if}
                </div>
            {/if}

            {#if note}
                <p class="text-xs leading-relaxed text-slate-600 dark:text-slate-400">{note}</p>
            {/if}
        </div>

        {#if onRetry}
        <div class="flex items-center justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-700" data-diagnostic-actions>
            <button type="button" class="btn btn-primary min-h-11 px-5 py-2.5" disabled={busy} onclick={onRetry}>
                {busy
                    ? (runningLabel ?? $_('common.testing', { default: 'Testing' }))
                    : result ? $_('common.test_again', { default: 'Test again' }) : (retryLabel ?? $_('common.test', { default: 'Test' }))}
            </button>
        </div>
        {/if}
    </div>
</div>
