<script lang="ts">
    import { getThumbnailUrl } from '../api';
    import { _ } from 'svelte-i18n';

    interface Props {
        /** The Frigate event the filter rejected. It has no detection record. */
        eventId: string;
        label: string | null;
        onopen?: () => void;
    }

    let { eventId, label, onopen }: Props = $props();

    // Matches DetectionPreview: a pointer travelling from the thumbnail into the
    // panel crosses a gap, and closing on the first mouseleave would put the panel
    // out of reach (WCAG 2.2 SC 1.4.13, "hoverable").
    const CLOSE_GRACE_MS = 120;

    let open = $state(false);
    let failed = $state(false);
    let rootEl = $state<HTMLElement | null>(null);
    let closeTimer: ReturnType<typeof setTimeout> | null = null;

    function show(): void {
        if (closeTimer) {
            clearTimeout(closeTimer);
            closeTimer = null;
        }
        open = true;
    }

    function hide(immediate = false): void {
        if (closeTimer) clearTimeout(closeTimer);
        if (immediate) {
            closeTimer = null;
            open = false;
            return;
        }
        closeTimer = setTimeout(() => {
            open = false;
            closeTimer = null;
        }, CLOSE_GRACE_MS);
    }

    function handleFocusOut(event: FocusEvent): void {
        const next = event.relatedTarget;
        if (next instanceof Node && rootEl?.contains(next)) return;
        hide(true);
    }

    function handleKeydown(event: KeyboardEvent): void {
        if (event.key === 'Escape' && open) {
            event.preventDefault();
            event.stopPropagation();
            hide(true);
        }
    }

    $effect(() => {
        return () => {
            if (closeTimer) clearTimeout(closeTimer);
        };
    });

    const name = $derived(label ?? $_('common.unknown_species', { default: 'Unknown species' }));
</script>

<div
    bind:this={rootEl}
    class="relative flex items-center"
    data-filtered-frame-preview
    onmouseenter={show}
    onmouseleave={() => hide()}
    onfocusin={show}
    onfocusout={handleFocusOut}
    onkeydown={handleKeydown}
    role="presentation"
>
    <button
        type="button"
        class="grid min-h-11 min-w-11 place-items-center rounded-lg focus-ring"
        aria-expanded={open}
        onclick={() => onopen?.()}
    >
        <span class="sr-only">
            {$_('jobs.errors_filtered_preview', {
                values: { species: name },
                default: 'Preview the frame filtered as {species}'
            })}
        </span>
        {#if failed}
            <!-- Frigate rotates short events away quickly, so a missing frame degrades to a
                 placeholder of identical size rather than a hole that shifts the row. -->
            <span
                class="flex h-9 w-9 items-center justify-center rounded-lg border-2 border-white bg-slate-100 text-slate-300 dark:border-slate-900 dark:bg-slate-800 dark:text-slate-600"
                aria-hidden="true"
            >
                <svg class="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="1.5">
                    <path stroke-linecap="round" stroke-linejoin="round" d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2 1.586-1.586a2 2 0 012.828 0L20 14M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </span>
        {:else}
            <img
                src={getThumbnailUrl(eventId)}
                alt=""
                loading="lazy"
                class="h-9 w-9 rounded-lg border-2 border-white object-cover opacity-80 dark:border-slate-900"
                onerror={() => (failed = true)}
            />
        {/if}
    </button>

    {#if open}
        <div
            class="absolute bottom-full left-0 z-30 mb-2 w-56 rounded-2xl border border-slate-200 bg-white p-2 shadow-xl motion-safe:animate-in dark:border-slate-700 dark:bg-slate-900"
            role="presentation"
        >
            {#if failed}
                <div class="grid aspect-video place-items-center rounded-xl bg-slate-100 px-3 text-center text-[11px] font-medium text-slate-500 dark:bg-slate-800 dark:text-slate-400">
                    {$_('jobs.errors_filtered_frame_gone', { default: 'Frigate no longer has this frame' })}
                </div>
            {:else}
                <img
                    src={getThumbnailUrl(eventId)}
                    alt=""
                    loading="lazy"
                    class="aspect-video w-full rounded-xl object-cover"
                    onerror={() => (failed = true)}
                />
            {/if}
            <p class="mt-1.5 px-0.5 text-[11px] font-semibold italic text-slate-600 dark:text-slate-300">{name}</p>
            <p class="px-0.5 font-mono text-[10px] text-slate-400 dark:text-slate-500">{eventId}</p>
        </div>
    {/if}
</div>
