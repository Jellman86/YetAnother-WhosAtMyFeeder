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
                return 'bg-emerald-500 border-emerald-600';
            case 'error':
                return 'bg-red-500 border-red-600';
            case 'warning':
                return 'bg-amber-500 border-amber-600';
            case 'info':
            default:
                return 'bg-teal-500 border-teal-600';
        }
    }
</script>

<!-- Toast Container -->
<div class="fixed top-4 right-4 z-[100] flex flex-col gap-2 pointer-events-none">
    {#each toasts as toast (toast.id)}
        <div
            class="pointer-events-auto max-w-md {getColorClasses(toast.type)} text-white rounded-xl shadow-lg border-2 backdrop-blur-sm"
            transition:fly={{ x: 300, duration: 300 }}
        >
            <div class="flex items-center gap-3 p-4">
                <!-- Icon -->
                <div class="flex-shrink-0 w-6 h-6 rounded-full bg-white/20 flex items-center justify-center text-sm font-black">
                    {getIcon(toast.type)}
                </div>

                <!-- Message -->
                <div class="flex-1 text-sm font-medium">
                    {toast.message}
                </div>

                <!-- Close Button -->
                <button
                    onclick={() => toastStore.remove(toast.id)}
                    class="flex-shrink-0 w-6 h-6 rounded-full hover:bg-white/20 flex items-center justify-center transition-colors"
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
    /* Additional styles if needed */
</style>
