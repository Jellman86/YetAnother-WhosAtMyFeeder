<script lang="ts">
    import { fly } from 'svelte/transition';
    import { _ } from 'svelte-i18n';
    import { toastStore, type Toast } from '../stores/toast.svelte';

    const errorToasts = $derived(toastStore.toasts.filter((toast) => toast.type === 'error'));
    const statusToasts = $derived(toastStore.toasts.filter((toast) => toast.type !== 'error'));

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

{#snippet toastCard(toast: Toast)}
    <!-- Pointing at or focusing a toast holds its countdown, so it never vanishes while being read. -->
    <div
        class="toast-card pointer-events-auto w-full max-w-md {getColorClasses(toast.type)} text-white rounded-xl shadow-lg border-2 backdrop-blur-sm"
        transition:fly={{ x: 300, duration: 300 }}
        role="group"
        aria-atomic="true"
        data-toast={toast.type}
        onmouseenter={() => toastStore.pause(toast.id)}
        onmouseleave={() => toastStore.resume(toast.id)}
        onfocusin={() => toastStore.pause(toast.id)}
        onfocusout={(event) => {
            if (!(event.currentTarget as HTMLElement).contains(event.relatedTarget as Node | null)) toastStore.resume(toast.id);
        }}
    >
        <div class="toast-row flex items-center gap-3 p-4">
            <!-- Icon -->
            <div class="flex-shrink-0 w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-sm font-bold" aria-hidden="true">
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
                <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>
        </div>
    </div>
{/snippet}

<!-- Toast Container. Errors are announced at once and stay until closed; everything else is
     announced politely and leaves on its own. Both regions are always present, so a screen
     reader is already listening when the first toast arrives. -->
<div
    data-toast-container
    class="toast-container z-[100] flex flex-col items-end gap-2 pointer-events-none"
>
    <div class="flex w-full flex-col items-end gap-2" role="alert" data-toast-region="errors">
        {#each errorToasts as toast (toast.id)}
            {@render toastCard(toast)}
        {/each}
    </div>
    <div class="flex w-full flex-col items-end gap-2" aria-live="polite" aria-relevant="additions" data-toast-region="status">
        {#each statusToasts as toast (toast.id)}
            {@render toastCard(toast)}
        {/each}
    </div>
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
