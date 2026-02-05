<script lang="ts">
    import { authStore } from '../stores/auth.svelte';

    let username = $state('admin');
    let password = $state('');
    let confirmPassword = $state('');
    let skipAuth = $state(false);
    let isLoading = $state(false);
    let error = $state<string | null>(null);

    async function handleSubmit(e: Event) {
        e.preventDefault();
        error = null;

        if (!skipAuth) {
            if (password !== confirmPassword) {
                error = "Passwords don't match";
                return;
            }
            if (password.length < 8) {
                error = 'Password must be at least 8 characters';
                return;
            }
        }

        isLoading = true;
        try {
            await authStore.completeInitialSetup({
                username: username.trim() || 'admin',
                password: skipAuth ? null : password,
                enableAuth: !skipAuth
            });
        } catch (err) {
            error = err instanceof Error ? err.message : 'Setup failed';
        } finally {
            isLoading = false;
        }
    }
</script>

<div class="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-900 px-4">
    <div class="max-w-lg w-full space-y-8 bg-white dark:bg-surface-800 p-8 rounded-xl shadow-lg border border-surface-200 dark:border-surface-700">
        <div class="text-center space-y-2">
            <h1 class="text-3xl font-bold text-gray-900 dark:text-white">Welcome to YA-WAMF</h1>
            <p class="text-sm text-gray-600 dark:text-gray-400">
                Secure your installation by setting an admin password.
            </p>
        </div>

        <form class="space-y-6" onsubmit={handleSubmit}>
            {#if !skipAuth}
                <div>
                    <label for="username" class="text-sm font-medium text-gray-700 dark:text-gray-300">Admin Username</label>
                    <input
                        id="username"
                        name="username"
                        type="text"
                        required
                        bind:value={username}
                        class="input-base mt-1"
                    />
                </div>

                <div>
                    <label for="password" class="text-sm font-medium text-gray-700 dark:text-gray-300">Password</label>
                    <input
                        id="password"
                        name="password"
                        type="password"
                        required
                        minlength="8"
                        bind:value={password}
                        class="input-base mt-1"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">Minimum 8 characters</p>
                </div>

                <div>
                    <label for="confirm-password" class="text-sm font-medium text-gray-700 dark:text-gray-300">Confirm Password</label>
                    <input
                        id="confirm-password"
                        name="confirm-password"
                        type="password"
                        required
                        minlength="8"
                        bind:value={confirmPassword}
                        class="input-base mt-1"
                    />
                </div>
            {/if}

            {#if error}
                <div class="rounded-md bg-red-50 dark:bg-red-900/20 p-3 text-sm text-red-700 dark:text-red-200">
                    {error}
                </div>
            {/if}

            <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300 border-t border-slate-200 dark:border-slate-700 pt-4">
                <input
                    type="checkbox"
                    bind:checked={skipAuth}
                    class="rounded border-slate-300 text-teal-600 focus:ring-teal-500"
                />
                Skip authentication (not recommended)
            </label>

            <button
                type="submit"
                disabled={isLoading}
                class="btn btn-primary w-full py-3"
            >
                {#if isLoading}
                    Setting up...
                {:else}
                    {#if skipAuth}
                        Continue without password
                    {:else}
                        Set password and continue
                    {/if}
                {/if}
            </button>
        </form>
    </div>
</div>
