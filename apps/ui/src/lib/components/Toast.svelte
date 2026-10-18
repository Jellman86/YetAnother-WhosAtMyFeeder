<script lang="ts">
    import { fade, fly } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { toastStore, type Toast } from '../stores/toast.svelte';

    // Get toasts from store
    let toasts = $derived(toastStore.toasts);

    function getIcon(type: Toast['type']) {
        switch (type) {
            case 'success':
                return '✓';
            case 'error':
                return '✕';
            case 'warning':
                return '⚠';
            case 'info':
            default:
                return 'i';
        }
    }

    function getColorClasses(type: Toast['type']) {
        switch (type) {
            case 'success':
                return 'bg-accent-700 border-accent-800';
            case 'error':
                return 'bg-red-700 border-red-800';
            case 'warning':
                return 'bg-amber-700 border-amber-800';
            case 'info':
            default:
                return 'bg-brand-700 border-brand-800';
        }
    }
</script>

<!-- Toast Container -->
<div
    data-toast-container
    class="toast-container z-[100] flex flex-col items-end gap-2 pointer-events-none"
    aria-live="polite"
    aria-relevant="additions"
>
    {#each toasts as toast (toast.id)}
        <div
            class="toast-card pointer-events-auto w-full max-w-md {getColorClasses(toast.type)} text-white rounded-xl shadow-lg border-2 backdrop-blur-sm"
            transition:fly={{ x: 300, duration: 300 }}
            aria-atomic="true"
        >
            <div class="toast-row flex items-center gap-3 p-4">
                <!-- Icon -->
                <div class="flex-shrink-0 w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-sm font-bold">
                    {getIcon(toast.type)}
                </div>

                <!-- Message -->
                <div class="toast-message min-w-0 flex-1 break-words text-sm font-medium">
                    {toast.message}
                </div>

                <!-- Close Button -->
                <button
                    onclick={() => toastStore.remove(toast.id)}
                    class="-mr-2 inline-flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full transition-colors hover:bg-white/20 focus:outline-none focus-visible:ring-2 focus-visible:ring-white/70"
                    aria-label={$_('notifications.close_toast', { default: 'Close notification' })}
                >
                    <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                </button>
            </div>
        </div>
    {/each}
</div>

<style>
    .toast-container {
        position: fixed;
        top: calc(env(safe-area-inset-top, 0px) + 5rem);
        right: 1rem;
        left: 1rem;
    }

    @media (min-width: 640px) {
        .toast-container {
            top: 1rem;
            left: auto;
        }
    }

    /* With enlarged text a phone has no room for icon, words and the close
       button on one line, so the words take their own line under the other two.
       Only below 640px, where the stack spans the screen: wider screens size it to
       the toasts, which a size container would collapse. */
    @media (max-width: 639px) {
        .toast-card {
            container-type: inline-size;
        }
    }

    @container (max-width: 16rem) {
        .toast-row {
            flex-wrap: wrap;
            justify-content: space-between;
        }

        .toast-message {
            order: 1;
            flex-basis: 100%;
        }
    }
</style>
