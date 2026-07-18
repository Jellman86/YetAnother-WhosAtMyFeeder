<script lang="ts">
    import { _ } from 'svelte-i18n';
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

    let unavailable = $derived(mode === 'unavailable');
    let manualRetrying = $state(false);
    let busy = $derived(retrying || manualRetrying);

    async function handleRetry() {
        if (busy || !onRetry) return;
        manualRetrying = true;
        try {
            await onRetry();
        } finally {
            manualRetrying = false;
        }
    }
</script>

<main
    id="main-content"
    class="relative flex min-h-screen items-center justify-center overflow-hidden bg-surface-light px-4 py-10 text-slate-900 dark:bg-surface-dark dark:text-white sm:px-6"
>
    <div class="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-teal-100/70 to-transparent dark:from-teal-950/30" aria-hidden="true"></div>
    <div class="pointer-events-none absolute -right-24 top-1/3 h-64 w-64 rounded-full bg-emerald-100/40 blur-3xl dark:bg-emerald-950/20" aria-hidden="true"></div>

    <section
        class="relative w-full max-w-2xl overflow-hidden rounded-3xl border border-slate-200/80 bg-white/95 shadow-xl ring-1 ring-slate-900/5 dark:border-slate-700/70 dark:bg-slate-900/95 dark:ring-white/5"
        role={unavailable ? 'alert' : 'status'}
        aria-live={unavailable ? 'assertive' : 'polite'}
        aria-busy={busy || !unavailable}
    >
        <header class="flex items-center justify-between gap-4 bg-gradient-to-r from-teal-50 via-emerald-50/70 to-white px-6 py-4 dark:from-teal-950/40 dark:via-emerald-950/20 dark:to-slate-900 sm:px-8">
            <div class="flex min-w-0 items-center gap-3">
                <img src={APP_ICON_192_URL} alt="" class="h-9 w-9 shrink-0 object-contain" />
                <div class="min-w-0">
                    <p class="truncate font-display text-sm font-bold tracking-tight text-teal-800 dark:text-teal-200">YA-WAMF</p>
                    <p class="truncate text-xs font-medium text-slate-500 dark:text-slate-400">
                        {$_('auth.status_check_eyebrow', { default: 'Service connection' })}
                    </p>
                </div>
            </div>

            <div class="inline-flex shrink-0 items-center gap-2 rounded-full border px-3 py-1.5 text-xs font-bold {unavailable ? 'border-amber-200 bg-amber-50 text-amber-800 dark:border-amber-800/70 dark:bg-amber-950/40 dark:text-amber-200' : 'border-teal-200 bg-teal-50 text-teal-800 dark:border-teal-800/70 dark:bg-teal-950/40 dark:text-teal-200'}">
                <span class="relative flex h-2 w-2" aria-hidden="true">
                    <span class="absolute inline-flex h-full w-full rounded-full opacity-60 motion-safe:animate-ping {unavailable ? 'bg-amber-500' : 'bg-teal-500'}"></span>
                    <span class="relative inline-flex h-2 w-2 rounded-full {unavailable ? 'bg-amber-600 dark:bg-amber-400' : 'bg-teal-600 dark:bg-teal-400'}"></span>
                </span>
                {unavailable
                    ? $_('auth.status_unavailable_badge', { default: 'Not responding' })
                    : $_('auth.status_checking_badge', { default: 'Checking' })}
            </div>
        </header>

        <div class="px-6 py-8 sm:px-8 sm:py-10">
            <div class="grid gap-6 sm:grid-cols-[4rem_minmax(0,1fr)] sm:gap-8">
                <div class="flex h-16 w-16 items-center justify-center rounded-2xl border border-slate-200 bg-slate-50 text-slate-500 shadow-sm dark:border-slate-700 dark:bg-slate-800/80 dark:text-slate-300" aria-hidden="true">
                    {#if unavailable}
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
                        {unavailable
                            ? $_('auth.status_unavailable_title', { default: "YA-WAMF isn't responding yet" })
                            : $_('auth.loading_status', { default: 'Starting YA-WAMF' })}
                    </h1>
                    <p class="mt-3 max-w-xl text-base leading-7 text-slate-600 dark:text-slate-300">
                        {unavailable
                            ? $_('auth.status_unavailable_desc', { default: 'The service may still be starting after an update or model change. Your feeder data is safe while it comes back online.' })
                            : $_('auth.loading_status_desc', { default: 'Checking the service and your access settings before opening the feeder.' })}
                    </p>

                    {#if unavailable}
                        <div class="mt-6 border-l-2 border-teal-300 pl-4 dark:border-teal-700">
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
