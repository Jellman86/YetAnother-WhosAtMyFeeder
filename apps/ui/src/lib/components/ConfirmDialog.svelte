<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { confirmDialog } from '../stores/confirm_dialog.svelte';
    import { trapFocus } from '../utils/focus-trap';
    import { portal } from '../utils/portal';

    let dialogEl = $state<HTMLElement | null>(null);
    const pending = $derived(confirmDialog.current);

    $effect(() => {
        if (!pending || !dialogEl) return;
        const previouslyFocused = document.activeElement instanceof HTMLElement ? document.activeElement : null;
        // Cancel comes first, so the trap's initial focus lands on the safe answer.
        const releaseFocus = trapFocus(dialogEl);
        return () => {
            releaseFocus();
            previouslyFocused?.focus();
        };
    });

    function handleKeydown(event: KeyboardEvent) {
        // Keys answer this question only: no global shortcut fires behind it, and Escape
        // cancels without closing the modal it opened over.
        event.stopPropagation();
        if (event.key !== 'Escape') return;
        event.preventDefault();
        confirmDialog.answer(false);
    }
</script>

{#if pending}
    <div
        use:portal
        class="fixed inset-0 z-[95] flex items-center justify-center overflow-y-auto bg-slate-900/60 p-4 backdrop-blur-sm"
        role="presentation"
        onclick={(event) => {
            if (event.target === event.currentTarget) confirmDialog.answer(false);
        }}
    >
        <div
            bind:this={dialogEl}
            role="alertdialog"
            aria-modal="true"
            aria-labelledby="confirm-dialog-title"
            aria-describedby="confirm-dialog-message"
            tabindex="-1"
            onkeydown={handleKeydown}
            class="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-2xl dark:border-slate-700 dark:bg-slate-900"
        >
            <h2 id="confirm-dialog-title" class="text-base font-semibold text-slate-900 dark:text-white">
                {pending.title}
            </h2>
            <p id="confirm-dialog-message" class="mt-2 whitespace-pre-line text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                {pending.message}
            </p>
            <div class="mt-6 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
                <button
                    type="button"
                    class="btn btn-secondary min-h-11 px-4 text-sm"
                    onclick={() => confirmDialog.answer(false)}
                >
                    {$_('common.cancel')}
                </button>
                <button
                    type="button"
                    class="btn min-h-11 px-4 text-sm {pending.tone === 'danger' ? 'btn-danger' : 'btn-primary'}"
                    onclick={() => confirmDialog.answer(true)}
                >
                    {pending.confirmLabel}
                </button>
            </div>
        </div>
    </div>
{/if}
