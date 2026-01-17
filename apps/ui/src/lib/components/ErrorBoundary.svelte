<script lang="ts">
    import { _ } from 'svelte-i18n';

    let { children, fallback } = $props<{
        children: import('svelte').Snippet;
        fallback?: import('svelte').Snippet<[Error]>;
    }>();

    let error = $state<Error | null>(null);
    let errorInfo = $state<string>('');

    // Svelte 5 error boundary using onError lifecycle
    $effect(() => {
        const handleError = (event: ErrorEvent) => {
            // Only handle errors from our app, not from browser extensions, etc.
            if (event.filename && event.filename.includes('/src/')) {
                error = event.error || new Error(event.message);
                errorInfo = `${event.filename}:${event.lineno}:${event.colno}`;
                event.preventDefault();
                console.error('Error caught by boundary:', error, errorInfo);
            }
        };

        const handleRejection = (event: PromiseRejectionEvent) => {
            error = event.reason instanceof Error ? event.reason : new Error(String(event.reason));
            errorInfo = 'Unhandled Promise Rejection';
            event.preventDefault();
            console.error('Promise rejection caught by boundary:', error);
        };

        window.addEventListener('error', handleError);
        window.addEventListener('unhandledrejection', handleRejection);

        return () => {
            window.removeEventListener('error', handleError);
            window.removeEventListener('unhandledrejection', handleRejection);
        };
    });

    function resetError() {
        error = null;
        errorInfo = '';
    }

    function copyErrorToClipboard() {
        const errorText = `Error: ${error?.message}\n\nStack: ${error?.stack}\n\nInfo: ${errorInfo}`;
        navigator.clipboard.writeText(errorText).then(() => {
            alert('Error details copied to clipboard');
        });
    }
</script>

{#if error}
    {#if fallback}
        {@render fallback(error)}
    {:else}
        <!-- Default error UI -->
        <div class="min-h-screen bg-slate-50 dark:bg-slate-900 flex items-center justify-center p-4">
            <div class="max-w-2xl w-full bg-white dark:bg-slate-800 rounded-2xl shadow-xl p-8 border border-red-200 dark:border-red-800">
                <!-- Error Icon -->
                <div class="flex items-center justify-center w-16 h-16 bg-red-100 dark:bg-red-900/30 rounded-full mx-auto mb-6">
                    <svg xmlns="http://www.w3.org/2000/svg" class="h-8 w-8 text-red-600 dark:text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2">
                        <path stroke-linecap="round" stroke-linejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                </div>

                <!-- Error Title -->
                <h1 class="text-2xl font-bold text-center text-slate-900 dark:text-white mb-2">
                    {$_('error.boundary_title', { default: 'Something went wrong' })}
                </h1>

                <!-- Error Message -->
                <p class="text-center text-slate-600 dark:text-slate-400 mb-6">
                    {$_('error.boundary_subtitle', { default: 'An unexpected error occurred. Please try again or contact support if the problem persists.' })}
                </p>

                <!-- Error Details (collapsed) -->
                <details class="bg-slate-50 dark:bg-slate-900 rounded-lg p-4 mb-6">
                    <summary class="cursor-pointer font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white">
                        {$_('error.show_details', { default: 'Show error details' })}
                    </summary>
                    <div class="mt-4 space-y-2">
                        <div class="text-sm">
                            <strong class="text-slate-700 dark:text-slate-300">Error:</strong>
                            <pre class="mt-1 p-2 bg-white dark:bg-slate-800 rounded text-xs overflow-x-auto text-red-600 dark:text-red-400">{error.message}</pre>
                        </div>
                        {#if error.stack}
                            <div class="text-sm">
                                <strong class="text-slate-700 dark:text-slate-300">Stack trace:</strong>
                                <pre class="mt-1 p-2 bg-white dark:bg-slate-800 rounded text-xs overflow-x-auto text-slate-600 dark:text-slate-400 max-h-48">{error.stack}</pre>
                            </div>
                        {/if}
                        {#if errorInfo}
                            <div class="text-sm">
                                <strong class="text-slate-700 dark:text-slate-300">Location:</strong>
                                <pre class="mt-1 p-2 bg-white dark:bg-slate-800 rounded text-xs overflow-x-auto text-slate-600 dark:text-slate-400">{errorInfo}</pre>
                            </div>
                        {/if}
                    </div>
                </details>

                <!-- Action Buttons -->
                <div class="flex flex-col sm:flex-row gap-3">
                    <button
                        onclick={resetError}
                        class="flex-1 px-6 py-3 bg-brand-600 hover:bg-brand-700 text-white font-medium rounded-xl transition-colors focus-ring"
                    >
                        {$_('error.try_again', { default: 'Try Again' })}
                    </button>
                    <button
                        onclick={copyErrorToClipboard}
                        class="flex-1 px-6 py-3 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-900 dark:text-white font-medium rounded-xl transition-colors focus-ring"
                    >
                        {$_('error.copy_details', { default: 'Copy Error Details' })}
                    </button>
                    <button
                        onclick={() => window.location.reload()}
                        class="flex-1 px-6 py-3 bg-slate-200 dark:bg-slate-700 hover:bg-slate-300 dark:hover:bg-slate-600 text-slate-900 dark:text-white font-medium rounded-xl transition-colors focus-ring"
                    >
                        {$_('error.reload_page', { default: 'Reload Page' })}
                    </button>
                </div>
            </div>
        </div>
    {/if}
{:else}
    {@render children()}
{/if}
