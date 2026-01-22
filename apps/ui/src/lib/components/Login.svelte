<script lang="ts">
    import { authStore } from '../stores/auth.svelte';
    
    let username = $state('');
    let password = $state('');
    let error = $state('');
    let isLoading = $state(false);

    async function handleSubmit(e: Event) {
        e.preventDefault();
        if (!username.trim() || !password) return;

        isLoading = true;
        error = '';
        
        try {
            await authStore.login(username.trim(), password);
        } catch (err) {
            error = err instanceof Error ? err.message : 'Login failed';
            isLoading = false;
        }
    }
</script>

<div class="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-900 px-4">
    <div class="max-w-md w-full space-y-8 bg-white dark:bg-surface-800 p-8 rounded-xl shadow-lg border border-surface-200 dark:border-surface-700">
        <div class="text-center">
            <h2 class="mt-6 text-3xl font-bold text-gray-900 dark:text-white">Sign in</h2>
            <p class="mt-2 text-sm text-gray-600 dark:text-gray-400">
                Enter your admin credentials to access YA-WAMF.
            </p>
        </div>
        
        <form class="mt-8 space-y-6" onsubmit={handleSubmit}>
            <div>
                <label for="username" class="sr-only">Username</label>
                <input
                    id="username"
                    name="username"
                    type="text"
                    required
                    bind:value={username}
                    class="appearance-none rounded-lg relative block w-full px-3 py-3 border border-gray-300 dark:border-surface-600 placeholder-gray-500 text-gray-900 dark:text-white dark:bg-surface-700 focus:outline-none focus:ring-emerald-500 focus:border-emerald-500 sm:text-sm"
                    placeholder="Username"
                />
            </div>
            <div>
                <label for="password" class="sr-only">Password</label>
                <input
                    id="password"
                    name="password"
                    type="password"
                    required
                    bind:value={password}
                    class="appearance-none rounded-lg relative block w-full px-3 py-3 border border-gray-300 dark:border-surface-600 placeholder-gray-500 text-gray-900 dark:text-white dark:bg-surface-700 focus:outline-none focus:ring-emerald-500 focus:border-emerald-500 sm:text-sm"
                    placeholder="Password"
                />
            </div>

            {#if error}
                <div class="text-red-500 text-sm text-center bg-red-50 dark:bg-red-900/20 p-2 rounded">
                    {error}
                </div>
            {/if}

            <div>
                <button
                    type="submit"
                    disabled={isLoading}
                    class="group relative w-full flex justify-center py-3 px-4 border border-transparent text-sm font-medium rounded-md text-white bg-emerald-600 hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                    {#if isLoading}
                        <svg class="animate-spin -ml-1 mr-3 h-5 w-5 text-white" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
                            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        Verifying...
                    {:else}
                        Sign in
                    {/if}
                </button>
            </div>
        </form>
    </div>
</div>
