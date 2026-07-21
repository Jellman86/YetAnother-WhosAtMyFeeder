<script lang="ts">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchStartupStatus, type StartupPhase, type StartupStatus } from '../api';
    import { APP_ICON_192_URL } from '../assets';

    let {
        mode,
        retrying = false,
        onRetry
    }: {
        mode: 'loading' | 'unavailable';
        retrying?: boolean;
        onRetry?: () => Promise<void> | void;
    } = $props();

    const startupStatusPollMs = 1_000;
    const phaseFallbacks: Record<StartupPhase, string> = {
        launching: 'Launching application services',
        detecting_hardware: 'Checking available inference hardware',
        loading_model: 'Loading and checking the selected bird model',
        model_ready: 'Selected bird model is ready',
        database: 'Preparing detection history',
        starting_services: 'Starting event and media services',
        finalizing: 'Finishing startup checks',
        ready: 'Ready'
    };

    let startupStatus = $state<StartupStatus | null>(null);
    let startupStatusChecked = $state(false);
    let startupStatusRefresh: Promise<void> | null = null;
    let lastReadyRetryAt: string | null = null;
    let manualRetrying = $state(false);

    let startupActive = $derived(startupStatus?.status === 'starting');
    let startupFailed = $derived(startupStatus?.status === 'failed');
    let showingUnavailable = $derived(mode === 'unavailable' && startupStatusChecked && !startupActive && !startupFailed);
    let attentionNeeded = $derived(showingUnavailable || startupFailed);
    let busy = $derived(retrying || manualRetrying);
    let startupProgress = $derived(startupStatus?.progress ?? 0);
    let startupPhase = $derived(startupStatus?.phase ?? 'launching');
    let startupPhaseFallback = $derived(phaseFallbacks[startupPhase]);

    async function refreshStartupStatus(): Promise<void> {
        if (startupStatusRefresh) return startupStatusRefresh;
        const currentRefresh = (async () => {
            const nextStatus = await fetchStartupStatus();
            if (nextStatus) {
                startupStatus = nextStatus;
                if (
                    nextStatus.status === 'ready'
                    && mode === 'unavailable'
                    && onRetry
                    && nextStatus.updated_at !== lastReadyRetryAt
                ) {
                    lastReadyRetryAt = nextStatus.updated_at;
                    await onRetry();
                }
            }
            startupStatusChecked = true;
        })();
        startupStatusRefresh = currentRefresh;
        try {
            await currentRefresh;
        } finally {
            if (startupStatusRefresh === currentRefresh) startupStatusRefresh = null;
        }
    }

    async function handleRetry(): Promise<void> {
        if (busy || !onRetry) return;
        manualRetrying = true;
        try {
            await Promise.all([onRetry(), refreshStartupStatus()]);
        } finally {
            manualRetrying = false;
        }
    }

    onMount(() => {
        void refreshStartupStatus();
        const interval = window.setInterval(() => {
            if (!document.hidden) void refreshStartupStatus();
        }, startupStatusPollMs);
        const handleVisibilityChange = () => {
            if (!document.hidden) void refreshStartupStatus();
        };
        document.addEventListener('visibilitychange', handleVisibilityChange);
        return () => {
            window.clearInterval(interval);
            document.removeEventListener('visibilitychange', handleVisibilityChange);
        };
    });
</script>

<main
    id="main-content"
    class="relative flex min-h-screen items-center justify-center overflow-hidden bg-surface-light px-4 py-10 text-slate-900 dark:bg-surface-dark dark:text-white sm:px-6"
>
    <div class="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-brand-100/70 to-transparent dark:from-brand-950/30" aria-hidden="true"></div>
    <div class="pointer-events-none absolute -right-24 top-1/3 h-64 w-64 rounded-full bg-accent-100/40 blur-3xl dark:bg-accent-950/20" aria-hidden="true"></div>

    <section
        class="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-200/80 bg-white/95 shadow-xl ring-1 ring-slate-900/5 dark:border-slate-700/70 dark:bg-slate-900/95 dark:ring-white/5"
        role={showingUnavailable || startupFailed ? 'alert' : 'status'}
        aria-live={attentionNeeded ? 'assertive' : 'polite'}
        aria-busy={busy || startupActive || !startupStatusChecked}
    >
        <header class="flex items-center justify-between gap-4 bg-gradient-to-r from-brand-50 via-accent-50/70 to-white px-6 py-4 dark:from-brand-950/40 dark:via-accent-950/20 dark:to-slate-900 sm:px-8">
            <div class="flex min-w-0 items-center gap-3">
                <img src={APP_ICON_192_URL} alt="" class="h-9 w-9 shrink-0 object-contain" />
                <div class="min-w-0">
                    <p class="truncate font-display text-sm font-bold tracking-tight text-brand-800 dark:text-brand-200">YA-WAMF</p>
                    <p class="truncate text-xs font-medium text-slate-500 dark:text-slate-400">
                        {$_('auth.status_check_eyebrow', { default: 'Service connection' })}
                    </p>
                </div>
            </div>

            <div class="inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold {attentionNeeded ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-200' : 'border-brand-200 bg-brand-50 text-brand-800 dark:border-brand-800/70 dark:bg-brand-950/40 dark:text-brand-200'}">
                <span class="relative flex h-2 w-2" aria-hidden="true">
                    <span class="absolute inline-flex h-full w-full rounded-full opacity-60 motion-safe:animate-ping {attentionNeeded ? 'bg-amber-500' : 'bg-brand-500'}"></span>
                    <span class="relative inline-flex h-2 w-2 rounded-full {attentionNeeded ? 'bg-amber-600 dark:bg-amber-400' : 'bg-brand-600 dark:bg-brand-400'}"></span>
                </span>
                {startupActive
                    ? $_('auth.status_starting_badge', { default: 'Starting' })
                    : startupFailed
                        ? $_('auth.status_failed_badge', { default: 'Startup issue' })
                        : showingUnavailable
                            ? $_('auth.status_unavailable_badge', { default: 'Not responding' })
                            : $_('auth.status_checking_badge', { default: 'Checking' })}
            </div>
        </header>

        <div class="px-6 py-8 sm:px-8 sm:py-10">
            <div class="grid gap-6 sm:grid-cols-[4rem_minmax(0,1fr)] sm:gap-8">
                <div class="flex h-16 w-16 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-500 shadow-sm dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300" aria-hidden="true">
                    {#if attentionNeeded}
                        <svg class="h-8 w-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M7.5 6.5h9a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3h-9a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3Z" />
                            <path stroke-linecap="round" stroke-width="1.7" d="M8 12h.01M12 12h4M3 3l18 18" />
                        </svg>
                    {:else}
                        <svg class="h-8 w-8 motion-safe:animate-pulse" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.7" d="M7.5 6.5h9a3 3 0 0 1 3 3v5a3 3 0 0 1-3 3h-9a3 3 0 0 1-3-3v-5a3 3 0 0 1 3-3Z" />
                            <path stroke-linecap="round" stroke-width="1.7" d="M8 12h.01M12 12h4" />
                        </svg>
                    {/if}
                </div>

                <div class="min-w-0">
                    <h1 class="font-display text-2xl font-bold tracking-tight text-slate-950 dark:text-white sm:text-3xl">
                        {startupFailed
                            ? $_('auth.startup_failed_title', { default: 'YA-WAMF could not finish starting' })
                            : showingUnavailable
                                ? $_('auth.status_unavailable_title', { default: "YA-WAMF isn't responding yet" })
                                : $_('auth.loading_status', { default: 'Starting YA-WAMF' })}
                    </h1>
                    <p class="mt-3 max-w-xl text-base leading-7 text-slate-600 dark:text-slate-300">
                        {startupFailed
                            ? $_('auth.startup_failed_desc', { default: 'Startup stopped during a required check. Your feeder data is safe; check the container logs for the cause.' })
                            : showingUnavailable
                                ? $_('auth.status_unavailable_desc', { default: 'The service may still be starting after an update or model change. Your feeder data is safe while it comes back online.' })
                                : startupActive
                                    ? $_('auth.startup_status_desc', { default: 'Model loading and hardware checks can take longer after an update or model change. This progress comes directly from the container.' })
                                    : $_('auth.loading_status_desc', { default: 'Checking the service and your access settings before opening the feeder.' })}
                    </p>

                    {#if startupActive || startupFailed}
                        <div class="mt-7" aria-live="polite">
                            <div class="flex items-center justify-between gap-4 text-sm">
                                <span class="font-semibold text-slate-700 dark:text-slate-200">
                                    {$_('auth.startup_progress', { default: 'Startup progress' })}
                                </span>
                                <span class="font-mono text-xs font-bold tabular-nums text-slate-500 dark:text-slate-400">{startupProgress}%</span>
                            </div>
                            <div
                                class="mt-2 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
                                role="progressbar"
                                aria-label={$_('auth.startup_progress', { default: 'Startup progress' })}
                                aria-valuemin="0"
                                aria-valuemax="100"
                                aria-valuenow={startupProgress}
                            >
                                <div
                                    class="h-full w-full origin-left transform-gpu rounded-full motion-safe:transition-transform motion-safe:duration-300 {startupFailed ? 'bg-amber-500 dark:bg-amber-400' : 'bg-brand-600 dark:bg-brand-400'}"
                                    style={`transform: scaleX(${startupProgress / 100})`}
                                ></div>
                            </div>
                            <p class="mt-3 text-sm leading-6 text-slate-600 dark:text-slate-300">
                                {$_(`auth.startup_phase_${startupPhase}`, { default: startupPhaseFallback })}
                            </p>
                        </div>
                    {:else if !startupStatusChecked || mode === 'loading'}
                        <div class="mt-7">
                            <div
                                class="h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700"
                                role="progressbar"
                                aria-label={$_('auth.status_checking_badge', { default: 'Checking' })}
                            >
                                <div class="h-full w-1/3 rounded-full bg-brand-600 motion-safe:animate-pulse dark:bg-brand-400"></div>
                            </div>
                        </div>
                    {/if}

                    {#if showingUnavailable || startupFailed}
                        <div class="mt-6 border-l-2 border-brand-300 pl-4 dark:border-brand-700">
                            <p class="text-sm font-semibold text-slate-700 dark:text-slate-200">
                                {$_('auth.status_unavailable_auto_retry', { default: 'YA-WAMF checks again automatically every five seconds.' })}
                            </p>
                            <p class="mt-1 text-sm leading-6 text-slate-500 dark:text-slate-400">
                                {$_('auth.status_unavailable_help', { default: 'If it stays offline, check the container health and startup logs.' })}
                            </p>
                        </div>

                        <button
                            type="button"
                            class="btn btn-primary mt-7 min-h-11 px-5"
                            disabled={busy}
                            onclick={handleRetry}
                        >
                            {#if busy}
                                <svg class="h-4 w-4 motion-safe:animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                                    <circle class="opacity-30" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" />
                                    <path class="opacity-90" fill="currentColor" d="M21 12a9 9 0 0 0-9-9v3a6 6 0 0 1 6 6h3Z" />
                                </svg>
                                {$_('auth.status_checking_again', { default: 'Checking again…' })}
                            {:else}
                                <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 11a8.1 8.1 0 0 0-15.5-2M4 5v4h4M4 13a8.1 8.1 0 0 0 15.5 2M20 19v-4h-4" />
                                </svg>
                                {$_('auth.status_check_again', { default: 'Check again' })}
                            {/if}
                        </button>
                    {/if}
                </div>
            </div>
        </div>
    </section>
</main>
