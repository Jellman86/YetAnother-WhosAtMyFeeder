<script lang="ts" generics="DialogComponent">
    import { onMount, type Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { trapFocus } from '../utils/focus-trap';
    import { portal } from '../utils/portal';

    /**
     * A dialog whose code arrives on first open. The opener keeps focus while it loads; a slow load
     * says it is opening, and a failed one says so in words, with a retry and a way out.
     */
    let {
        loader,
        onclose,
        children
    }: {
        loader: () => Promise<{ default: DialogComponent }>;
        onclose: () => void;
        children: Snippet<[DialogComponent]>;
    } = $props();

    // Quick loads open with no flash of an intermediate state.
    const LOADING_NOTICE_DELAY_MS = 160;

    let dialog = $state.raw<DialogComponent | null>(null);
    let failed = $state(false);
    let showLoading = $state(false);
    let errorPanel = $state<HTMLElement | null>(null);
    let attempt = 0;
    let loadingTimer: ReturnType<typeof setTimeout> | null = null;

    function clearLoadingTimer(): void {
        if (loadingTimer !== null) clearTimeout(loadingTimer);
        loadingTimer = null;
    }

    async function load(): Promise<void> {
        const current = ++attempt;
        failed = false;
        showLoading = false;
        clearLoadingTimer();
        loadingTimer = setTimeout(() => {
            if (current === attempt) showLoading = true;
        }, LOADING_NOTICE_DELAY_MS);
        try {
            const module = await loader();
            if (current === attempt) dialog = module.default;
        } catch {
            if (current === attempt) failed = true;
        } finally {
            if (current === attempt) {
                clearLoadingTimer();
                showLoading = false;
            }
        }
    }

    $effect(() => {
        if (!errorPanel) return;
        return trapFocus(errorPanel);
    });

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key !== 'Escape') return;
        event.preventDefault();
        event.stopPropagation();
        onclose();
    }

    onMount(() => {
        void load();
        return () => {
            attempt += 1;
            clearLoadingTimer();
        };
    });
</script>

<!-- Focus stays on the opener while the code loads, so Escape is heard from the window then. -->
<svelte:window onkeydown={(event) => { if (!dialog && !failed) handleKeydown(event); }} />

{#if dialog}
    {@render children(dialog)}
{:else if failed}
    <div
        use:portal
        class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/65 p-4 backdrop-blur-sm"
        role="presentation"
        onclick={(event) => {
            if (event.target === event.currentTarget) onclose();
        }}
    >
        <div
            bind:this={errorPanel}
            data-lazy-modal-error
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="lazy-modal-error-title"
            aria-describedby="lazy-modal-error-description"
            tabindex="-1"
            onkeydown={handleKeydown}
            class="card-base w-full max-w-md p-6 shadow-2xl"
        >
            <h2 id="lazy-modal-error-title" class="text-base font-semibold text-slate-900 dark:text-white">
                {$_('lazy_modal.error_title', { default: 'This could not be opened' })}
            </h2>
            <p id="lazy-modal-error-description" class="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                {$_('lazy_modal.error_description', {
                    default: 'Part of the app did not arrive. Check your connection, then try again.'
                })}
            </p>
            <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button type="button" class="btn btn-secondary min-h-11 px-4 text-sm" onclick={onclose}>
                    {$_('common.close', { default: 'Close' })}
                </button>
                <button type="button" class="btn btn-primary min-h-11 px-4 text-sm" onclick={() => void load()}>
                    {$_('route_load.retry', { default: 'Try opening again' })}
                </button>
            </div>
        </div>
    </div>
{:else if showLoading}
    <div
        use:portal
        data-lazy-modal-loading
        class="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/40 p-4"
        role="presentation"
    >
        <p
            class="card-base flex items-center gap-3 px-5 py-4 text-sm font-medium text-slate-600 shadow-2xl dark:text-slate-300"
            role="status"
            aria-live="polite"
        >
            <svg class="h-4 w-4 motion-safe:animate-spin" fill="none" viewBox="0 0 24 24" aria-hidden="true">
                <circle class="opacity-25" cx="12" cy="12" r="9" stroke="currentColor" stroke-width="3" />
                <path class="opacity-80" fill="currentColor" d="M21 12a9 9 0 0 0-9-9v3a6 6 0 0 1 6 6h3Z" />
            </svg>
            {$_('lazy_modal.loading', { default: 'Opening…' })}
        </p>
    </div>
{/if}
