<script lang="ts">
    import type { Snippet } from 'svelte';
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { trapFocus } from '../utils/focus-trap';
    import { portal } from '../utils/portal';
    import type { DiagnosticStage, DiagnosticStageState, DiagnosticResult } from '../utils/diagnostic-runner';

    interface Props {
        title: string;
        subtitle?: string;
        // Small uppercase brand label above the title. Defaults to the product name.
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
        eyebrow = 'YA-WAMF',
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
    const resolvedCount = $derived(stages.filter((s) => s.state !== 'pending').length);
    const revealed = $derived(Math.min(resolvedCount, tick));

    $effect(() => {
        // Restart the reveal whenever a new run begins.
        void runId;
        tick = 0;
        const timer = setInterval(() => {
            tick += 1;
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

    const completed = $derived(displayStages.filter((s) => s.state === 'passed' || s.state === 'failed').length);
    const progress = $derived(stages.length === 0 ? 0 : Math.round((completed / stages.length) * 100));

    onMount(() => {
        const previousOverflow = document.body.style.overflow;
        document.body.style.overflow = 'hidden';
        const releaseFocus = modalElement ? trapFocus(modalElement) : () => {};
        return () => {
            releaseFocus();
            document.body.style.overflow = previousOverflow;
        };
    });

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape') onClose();
    }

    function stageIcon(state: DiagnosticStageState): string {
        if (state === 'passed') return '✓';
        if (state === 'failed') return '!';
        if (state === 'skipped') return '–';
        return '';
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<div
    use:portal
    class="fixed inset-0 z-[80] flex items-center justify-center overflow-y-auto bg-gradient-to-br from-slate-900/65 to-teal-950/55 p-4 backdrop-blur-sm"
    role="presentation"
>
    <div
        bind:this={modalElement}
        role="dialog"
        aria-modal="true"
        aria-labelledby="diagnostic-title"
        aria-describedby="diagnostic-description"
        tabindex="-1"
        class="my-8 w-full max-w-2xl overflow-hidden rounded-3xl border border-white/10 bg-white shadow-2xl ring-1 ring-black/5 dark:bg-slate-900"
    >
        <header class="space-y-4 bg-gradient-to-r from-teal-50 via-emerald-50 to-white px-6 py-5 dark:from-teal-950/45 dark:via-emerald-950/20 dark:to-slate-900">
            <div class="flex items-start justify-between gap-4">
                <div class="space-y-1">
                    <p class="text-[10px] font-black uppercase tracking-[0.22em] text-teal-700 dark:text-teal-300">{eyebrow}</p>
                    <h2 id="diagnostic-title" class="text-2xl font-black tracking-tight text-slate-900 dark:text-white">
                        {title}
                    </h2>
                    {#if subtitle}
                        <p id="diagnostic-description" class="text-sm text-slate-600 dark:text-slate-300">{subtitle}</p>
                    {/if}
                </div>
                <button type="button" class="btn btn-ghost p-2" aria-label={closeLabel ?? $_('common.close', { default: 'Close' })} onclick={onClose}>✕</button>
            </div>

            <div class="flex items-center gap-1.5" aria-hidden="true">
                {#each displayStages as stage}
                    <span class="h-1.5 flex-1 rounded-full transition-colors duration-300 {stage.state === 'passed' ? 'bg-teal-500' : stage.state === 'failed' ? 'bg-red-500' : stage.state === 'running' ? 'animate-pulse bg-teal-400' : 'bg-slate-200 dark:bg-slate-700'}"></span>
                {/each}
            </div>
            <span class="sr-only" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100">{progress}%</span>
        </header>

        <div class="max-h-[68vh] space-y-4 overflow-y-auto p-6" aria-live="polite">
            {#if summary}
                <div class="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-sm">
                    {@render summary()}
                </div>
            {/if}

            <ol class="divide-y divide-slate-100 overflow-hidden rounded-2xl border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
                {#each displayStages as stage, index}
                    <li class="flex items-start gap-3 p-3.5 {stage.state === 'failed' ? 'bg-red-50/70 dark:bg-red-950/20' : stage.state === 'running' ? 'bg-teal-50/60 dark:bg-teal-950/15' : ''}">
                        <span class="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full text-xs font-black {stage.state === 'failed' ? 'bg-red-600 text-white' : stage.state === 'passed' ? 'bg-emerald-600 text-white' : stage.state === 'running' ? 'animate-pulse bg-teal-500 text-white' : 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-300'}">
                            {stageIcon(stage.state) || index + 1}
                        </span>
                        <div class="min-w-0 flex-1 space-y-0.5">
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="text-sm font-bold text-slate-900 dark:text-white">{stage.label}</h3>
                                {#if stage.state === 'running'}
                                    <span class="text-[10px] font-black uppercase tracking-widest text-teal-700 dark:text-teal-300">{runningLabel ?? $_('common.testing', { default: 'Testing' })}</span>
                                {/if}
                            </div>
                            {#if stage.state !== 'pending'}
                                <p class="text-xs leading-relaxed text-slate-600 dark:text-slate-300">{stage.message}</p>
                            {/if}
                        </div>
                    </li>
                {/each}
            </ol>

            {#if result && revealed >= resolvedCount}
                <div role="status" class="rounded-2xl border p-4 {result.ok ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-100' : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100'}">
                    <p class="font-bold">{result.message}</p>
                    {#if result.hint}
                        <p class="mt-1 text-sm">{result.hint}</p>
                    {/if}
                </div>
            {/if}

            {#if note}
                <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">{note}</p>
            {/if}
        </div>

        <footer class="flex items-center justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-700">
            <button type="button" class="btn btn-ghost px-4 py-2.5" onclick={onClose}>{closeLabel ?? $_('common.close', { default: 'Close' })}</button>
            {#if onRetry}
                <button type="button" class="btn btn-primary px-5 py-2.5" disabled={busy} onclick={onRetry}>
                    {busy ? (runningLabel ?? $_('common.testing', { default: 'Testing' })) : (retryLabel ?? $_('common.test', { default: 'Test' }))}
                </button>
            {/if}
        </footer>
    </div>
</div>
