<script lang="ts">
    import DialogCloseButton from './DialogCloseButton.svelte';
    import StatusIcon from './ui/StatusIcon.svelte';
    import { TONE_CHIP, TONE_INK, TONE_MARK, type Tone } from './ui/tone';
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

    /** A step's tone: green passed, amber warned (it needs a look), rose failed, brand running. */
    function stageTone(state: DiagnosticStageState): Tone {
        if (state === 'passed') return 'ok';
        if (state === 'failed') return 'fail';
        if (state === 'warning') return 'attention';
        if (state === 'running') return 'info';
        return 'neutral';
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<div
    use:portal
    class="fixed inset-0 z-80 flex items-center justify-center overflow-y-auto bg-media/60 p-4 backdrop-blur-xs"
    role="presentation"
>
    <div
        bind:this={modalElement}
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnostic-title"
        aria-describedby={subtitle ? 'diagnostic-description' : undefined}
        tabindex="-1"
        class="my-8 w-full max-w-2xl overflow-hidden rounded-2xl border border-line-soft bg-surface shadow-2xl"
    >
        <!-- Plain divisions, not header and footer: the dialog is portalled to the body, where those
             elements would count as a second page banner and a second page footer. -->
        <div class="space-y-4 bg-surface-raised px-6 py-5">
            <div class="flex items-start justify-between gap-4">
                <div class="space-y-1">
                    {#if eyebrow}
                        <p class="text-xs font-semibold text-accent-ink">{eyebrow}</p>
                    {/if}
                    <h2 id="diagnostic-title" class="text-2xl font-bold tracking-tight text-strong">
                        {title}
                    </h2>
                    {#if subtitle}
                        <p id="diagnostic-description" class="text-sm text-muted">{subtitle}</p>
                    {/if}
                </div>
                <DialogCloseButton label={closeLabel} onclick={onClose} />
            </div>

            <div class="flex items-center gap-1.5" aria-hidden="true">
                {#each displayStages as stage}
                    <span class="h-1.5 flex-1 rounded-full transition-colors duration-300 {stage.state === 'pending' || stage.state === 'skipped' ? 'bg-line' : TONE_MARK[stageTone(stage.state)]} {stage.state === 'running' ? 'animate-pulse' : ''}"></span>
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

            <ol class="divide-y divide-line-soft overflow-hidden rounded-2xl border border-line">
                {#each displayStages as stage, index}
                    <li class="flex items-start gap-3 p-3.5 {stage.state === 'failed' ? 'bg-status-fail-soft' : stage.state === 'warning' ? 'bg-status-attention-soft' : stage.state === 'running' ? 'bg-status-info-soft' : ''}" data-diagnostic-stage-tone={stageTone(stage.state)}>
                        <!-- The step's shape says its outcome as well as its colour: a tick, a diamond, a cross, a disc. -->
                        {#if stage.state === 'pending'}
                            <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-xs font-bold {TONE_CHIP.neutral}">{index + 1}</span>
                        {:else}
                            <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center {TONE_INK[stageTone(stage.state)]} {stage.state === 'running' ? 'animate-pulse' : ''}">
                                <StatusIcon tone={stageTone(stage.state)} class="h-5 w-5" />
                            </span>
                        {/if}
                        <div class="min-w-0 flex-1 space-y-0.5">
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="text-sm font-bold text-strong">{stage.label}</h3>
                                {#if stage.state === 'running'}
                                    <span class="text-3xs font-bold text-accent-ink">{runningLabel ?? $_('common.testing', { default: 'Testing' })}</span>
                                {:else if stateWord(stage.state)}
                                    <span class="text-xs font-semibold {stage.state === 'failed' ? 'text-status-fail' : 'text-muted'}" data-diagnostic-stage-state={stage.state}>{stateWord(stage.state)}</span>
                                {/if}
                            </div>
                            {#if stage.state !== 'pending'}
                                <p class="text-xs leading-relaxed text-muted">{stage.message}</p>
                            {/if}
                            {#if stage.hint && (stage.state === 'failed' || stage.state === 'warning')}
                                <!-- A failure never ends on the failure: the next line says what to do about it. -->
                                <p class="text-xs font-semibold leading-relaxed text-strong" data-diagnostic-stage-hint>{stage.hint}</p>
                            {/if}
                        </div>
                    </li>
                {/each}
            </ol>

            {#if result && resultShown && summaryAddsSomething}
                <div data-diagnostic-result class="flex items-start gap-3 rounded-2xl border p-4 {result.ok ? 'border-status-ok-line bg-status-ok-soft' : 'border-status-fail-line bg-status-fail-soft'}">
                    <span class="mt-0.5 {TONE_INK[result.ok ? 'ok' : 'fail']}"><StatusIcon tone={result.ok ? 'ok' : 'fail'} class="h-5 w-5" /></span>
                    <div class="min-w-0 flex-1">
                        <p class="font-bold text-strong">{diagnosticHeadline(result, displayStages)}</p>
                        {#if result.hint}
                            <p class="mt-1 text-sm text-ink">{result.hint}</p>
                        {/if}
                    </div>
                </div>
            {/if}

            {#if note}
                <p class="text-xs leading-relaxed text-muted">{note}</p>
            {/if}
        </div>

        {#if onRetry}
        <div class="flex items-center justify-end gap-2 border-t border-line px-6 py-4" data-diagnostic-actions>
            <button type="button" class="btn btn-primary min-h-11 px-5 py-2.5" disabled={busy} onclick={onRetry}>
                {busy
                    ? (runningLabel ?? $_('common.testing', { default: 'Testing' }))
                    : result ? $_('common.test_again', { default: 'Test again' }) : (retryLabel ?? $_('common.test', { default: 'Test' }))}
            </button>
        </div>
        {/if}
    </div>
</div>
