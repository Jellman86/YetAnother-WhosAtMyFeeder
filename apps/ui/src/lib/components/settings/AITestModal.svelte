<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { LlmTestFailureStage, LlmTestResult } from '../../api/maintenance';
    import { trapFocus } from '../../utils/focus-trap';

    type StageState = 'pending' | 'running' | 'passed' | 'failed' | 'skipped';

    interface DiagnosticStage {
        id: LlmTestFailureStage;
        label: string;
        state: StageState;
        message: string;
    }

    let {
        provider,
        model,
        running,
        result,
        onClose,
        onRetry
    }: {
        provider: string;
        model: string;
        running: boolean;
        result: LlmTestResult | null;
        onClose: () => void;
        onRetry: () => void;
    } = $props();

    let modalElement = $state<HTMLElement | null>(null);

    const stageDefinitions = $derived([
        { id: 'configuration' as const, label: $_('settings.ai.test_stage_configuration', { default: 'Configuration' }) },
        { id: 'provider' as const, label: $_('settings.ai.test_stage_provider', { default: 'Provider availability' }) },
        { id: 'vision' as const, label: $_('settings.ai.test_stage_vision', { default: 'Vision input' }) },
        { id: 'multi_frame' as const, label: $_('settings.ai.test_stage_multiframe', { default: 'Multi-frame request' }) },
        { id: 'response' as const, label: $_('settings.ai.test_stage_response', { default: 'Model response' }) }
    ]);

    const stages = $derived.by((): DiagnosticStage[] => {
        if (running) {
            return stageDefinitions.map((stage, index) => ({
                ...stage,
                state: index === 0 ? 'passed' : index === 1 ? 'running' : 'pending',
                message: index === 0
                    ? $_('settings.ai.test_configuration_ok', { default: 'Provider, model, and credential are present.' })
                    : index === 1
                        ? $_('settings.ai.test_contacting', { default: 'Sending the bounded diagnostic request…' })
                        : $_('settings.ai.test_pending', { default: 'Waiting for the provider response.' })
            }));
        }

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

    const completedStages = $derived(stages.filter((stage) => stage.state === 'passed' || stage.state === 'failed').length);
    const progress = $derived(Math.round((completedStages / stages.length) * 100));

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

    function stageIcon(state: StageState): string {
        if (state === 'passed') return '✓';
        if (state === 'failed') return '!';
        if (state === 'skipped') return '–';
        return '';
    }
</script>

<svelte:window onkeydown={handleKeydown} />

<div
    class="fixed inset-0 z-[70] flex items-center justify-center overflow-y-auto bg-gradient-to-br from-slate-900/65 to-teal-950/55 p-4 backdrop-blur-sm"
    role="presentation"
>
    <div
        bind:this={modalElement}
        role="dialog"
        aria-modal="true"
        aria-labelledby="ai-test-title"
        aria-describedby="ai-test-description"
        tabindex="-1"
        class="my-8 w-full max-w-2xl overflow-hidden rounded-3xl border border-white/10 bg-white shadow-2xl ring-1 ring-black/5 dark:bg-slate-900"
    >
        <header class="space-y-4 bg-gradient-to-r from-teal-50 via-emerald-50 to-white px-6 py-5 dark:from-teal-950/45 dark:via-emerald-950/20 dark:to-slate-900">
            <div class="flex items-start justify-between gap-4">
                <div class="space-y-1">
                    <p class="text-[10px] font-black uppercase tracking-[0.22em] text-teal-700 dark:text-teal-300">YA-WAMF</p>
                    <h2 id="ai-test-title" class="text-2xl font-black tracking-tight text-slate-900 dark:text-white">
                        {$_('settings.ai.test_title', { default: 'AI model diagnostic' })}
                    </h2>
                    <p id="ai-test-description" class="text-sm text-slate-600 dark:text-slate-300">
                        {$_('settings.ai.test_subtitle', { default: 'Checking the same multi-frame vision format used for detection analysis.' })}
                    </p>
                </div>
                <button type="button" class="btn btn-ghost p-2" aria-label={$_('common.close', { default: 'Close' })} onclick={onClose}>✕</button>
            </div>

            <div class="flex items-center gap-1.5" aria-hidden="true">
                {#each stages as stage}
                    <span class="h-1.5 flex-1 rounded-full transition-colors duration-300 {stage.state === 'passed' ? 'bg-teal-500' : stage.state === 'failed' ? 'bg-red-500' : stage.state === 'running' ? 'animate-pulse bg-teal-400' : 'bg-slate-200 dark:bg-slate-700'}"></span>
                {/each}
            </div>
            <span class="sr-only" role="progressbar" aria-valuenow={progress} aria-valuemin="0" aria-valuemax="100">{progress}%</span>
        </header>

        <div class="max-h-[68vh] space-y-5 overflow-y-auto p-6" aria-live="polite">
            <div class="grid gap-3 rounded-2xl border border-slate-200 bg-slate-50 p-4 text-sm dark:border-slate-700 dark:bg-slate-950/40 sm:grid-cols-2">
                <div>
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-400">{$_('settings.llm.provider')}</p>
                    <p class="mt-1 font-bold text-slate-800 dark:text-slate-100">{provider}</p>
                </div>
                <div class="min-w-0">
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-400">{$_('settings.llm.model')}</p>
                    <p class="mt-1 truncate font-bold text-slate-800 dark:text-slate-100" title={model}>{model}</p>
                </div>
            </div>

            <ol class="space-y-3">
                {#each stages as stage, index}
                    <li class="flex gap-3 rounded-2xl border p-4 {stage.state === 'failed' ? 'border-red-200 bg-red-50 dark:border-red-900/60 dark:bg-red-950/20' : stage.state === 'passed' ? 'border-emerald-200 bg-emerald-50/70 dark:border-emerald-900/50 dark:bg-emerald-950/15' : 'border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900'}">
                        <span class="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sm font-black {stage.state === 'failed' ? 'bg-red-600 text-white' : stage.state === 'passed' ? 'bg-emerald-600 text-white' : stage.state === 'running' ? 'animate-pulse bg-teal-500 text-white' : 'bg-slate-200 text-slate-500 dark:bg-slate-700 dark:text-slate-300'}">
                            {stageIcon(stage.state) || index + 1}
                        </span>
                        <div class="min-w-0 space-y-1">
                            <div class="flex flex-wrap items-center gap-2">
                                <h3 class="font-bold text-slate-900 dark:text-white">{stage.label}</h3>
                                {#if stage.state === 'running'}
                                    <span class="text-[10px] font-black uppercase tracking-widest text-teal-700 dark:text-teal-300">{$_('settings.ai.test_running', { default: 'Testing' })}</span>
                                {/if}
                            </div>
                            <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-300">{stage.message}</p>
                        </div>
                    </li>
                {/each}
            </ol>

            {#if result}
                <div role="status" class="rounded-2xl border p-4 {result.status === 'ok' ? 'border-emerald-200 bg-emerald-50 text-emerald-900 dark:border-emerald-900/60 dark:bg-emerald-950/20 dark:text-emerald-100' : 'border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/20 dark:text-amber-100'}">
                    <p class="font-bold">{result.message}</p>
                    {#if result.retry_after_seconds}
                        <p class="mt-1 text-sm">{$_('settings.ai.test_retry_after', { values: { seconds: result.retry_after_seconds }, default: `Provider suggested retrying after ${result.retry_after_seconds} seconds.` })}</p>
                    {/if}
                </div>
            {/if}

            <p class="text-xs leading-relaxed text-slate-500 dark:text-slate-400">
                {$_('settings.ai.test_probe_note', { default: 'This sends five representative 1280×720 JPEG frames, matching the count, dimensions, and approximate payload size of a real analysis request.' })}
            </p>
        </div>

        <footer class="flex items-center justify-end gap-2 border-t border-slate-200 px-6 py-4 dark:border-slate-700">
            <button type="button" class="btn btn-ghost px-4 py-2.5" onclick={onClose}>{$_('common.close', { default: 'Close' })}</button>
            <button type="button" class="btn btn-primary px-5 py-2.5" disabled={running} onclick={onRetry}>
                {running ? $_('settings.ai.test_running', { default: 'Testing' }) : $_('settings.ai.test_retry', { default: 'Run test again' })}
            </button>
        </footer>
    </div>
</div>
