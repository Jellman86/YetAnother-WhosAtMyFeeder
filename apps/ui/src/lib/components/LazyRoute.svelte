<script lang="ts" generics="Props extends Record<string, unknown>">
    import { onMount } from 'svelte';
    import { _ } from 'svelte-i18n';
    import type { Component } from 'svelte';

    type PageModule = {
        default: Component<Props>;
    };

    let {
        loader,
        props,
        label,
        onLoadError
    }: {
        loader: () => Promise<PageModule>;
        props: Props;
        label: string;
        onLoadError?: (error: unknown) => void;
    } = $props();

    let pageModule = $state.raw<PageModule | null>(null);
    let loadError = $state.raw<unknown>(null);
    let showLoadingState = $state(false);
    let requestGeneration = 0;
    let loadingTimer: ReturnType<typeof setTimeout> | null = null;

    function clearLoadingTimer(): void {
        if (loadingTimer === null) return;
        clearTimeout(loadingTimer);
        loadingTimer = null;
    }

    async function loadPage(): Promise<void> {
        const generation = ++requestGeneration;
        clearLoadingTimer();
        pageModule = null;
        loadError = null;
        showLoadingState = false;
        loadingTimer = setTimeout(() => {
            if (generation === requestGeneration) showLoadingState = true;
        }, 160);

        try {
            const loadedPage = await loader();
            if (generation !== requestGeneration) return;
            pageModule = loadedPage;
        } catch (error: unknown) {
            if (generation !== requestGeneration) return;
            loadError = error;
            onLoadError?.(error);
        } finally {
            if (generation === requestGeneration) {
                clearLoadingTimer();
                showLoadingState = false;
            }
        }
    }

    onMount(() => {
        void loadPage();
        return () => {
            requestGeneration += 1;
            clearLoadingTimer();
        };
    });
</script>

{#if pageModule}
    {@const Page = pageModule.default}
    <Page {...props} />
{:else if loadError}
    <section
        class="my-6 border-y border-slate-200 py-8 dark:border-slate-700"
        role="alert"
        aria-live="assertive"
    >
        <div class="flex max-w-2xl items-start gap-4">
            <div
                class="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300"
                aria-hidden="true"
            >
                <svg class="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="1.8" d="M12 8v4m0 4h.01M10.3 4.6 3.5 16.4A2 2 0 0 0 5.2 19h13.6a2 2 0 0 0 1.7-2.6L13.7 4.6a2 2 0 0 0-3.4 0Z" />
                </svg>
            </div>
            <div class="min-w-0">
                <h2 class="font-display text-lg font-bold text-slate-900 dark:text-white">
                    {$_('route_load.error_title', { default: 'This page could not be opened' })}
                </h2>
                <p class="mt-1 text-sm leading-6 text-slate-600 dark:text-slate-300">
                    {$_('route_load.error_description', {
                        default: 'The page file did not arrive. Check your connection, then try again.'
                    })}
                </p>
                <button type="button" class="btn btn-secondary mt-4 min-h-11" onclick={loadPage}>
                    <svg class="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 11a8.1 8.1 0 0 0-15.5-2M4 5v4h4M4 13a8.1 8.1 0 0 0 15.5 2M20 19v-4h-4" />
                    </svg>
                    {$_('route_load.retry', { default: 'Try opening again' })}
                </button>
            </div>
        </div>
    </section>
{:else}
    <div class="min-h-24" aria-busy="true">
        {#if showLoadingState}
            <div
                class="flex items-center gap-3 border-t border-slate-200 py-6 text-sm font-medium text-slate-500 dark:border-slate-700 dark:text-slate-400"
                role="status"
                aria-live="polite"
            >
                <svg class="h-4 w-4 motion-safe:animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                    <circle class="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" />
                    <path class="opacity-80" fill="currentColor" d="M21 12a9 9 0 0 0-9-9v3a6 6 0 0 1 6 6h3Z" />
                </svg>
                {$_('route_load.loading', { default: 'Opening {page}…', values: { page: label } })}
            </div>
        {/if}
    </div>
{/if}
