<script lang="ts">
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { APP_ICON_192_URL } from '../assets';

    let username = $state('');
    let password = $state('');
    let error = $state('');
    let isLoading = $state(false);
    let passwordInput = $state<HTMLInputElement | null>(null);

    async function handleSubmit(e: Event) {
        e.preventDefault();
        if (!username.trim() || !password) return;

        isLoading = true;
        error = '';

        try {
            await authStore.login(username.trim(), password);
        } catch (err) {
            error = err instanceof Error && err.message
                ? err.message
                : $_('auth.login_failed', { default: 'Could not sign in. Check your username and password.' });
            isLoading = false;
            // The likeliest fix is retyping the password, so the cursor goes back there.
            passwordInput?.focus();
            passwordInput?.select();
        }
    }
</script>

<div class="flex min-h-screen items-center justify-center px-4 py-10">
    <div class="card-base w-full max-w-sm p-8">
        <div class="mb-8 text-center">
            <img src={APP_ICON_192_URL} alt="" width="56" height="56" class="mx-auto mb-4 h-14 w-14 object-contain" />
            <h1 class="font-display text-2xl font-bold text-slate-900 dark:text-white">
                {$_('auth.signin_heading', { default: 'Sign in' })}
            </h1>
            <p class="mt-2 text-sm text-slate-600 dark:text-slate-400">
                {$_('auth.signin_desc', { default: 'Sign in to manage your feeder.' })}
            </p>
        </div>

        <form class="space-y-5" onsubmit={handleSubmit} autocomplete="on">
            <div>
                <label for="username" class="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">{$_('auth.username')}</label>
                <input
                    id="username"
                    name="username"
                    aria-invalid={error ? 'true' : undefined}
                    aria-describedby={error ? 'login-error' : undefined}
                    type="text"
                    autocomplete="username"
                    required
                    bind:value={username}
                    class="input-base min-h-11"
                    placeholder={$_('auth.username_placeholder')}
                />
            </div>
            <div>
                <label for="password" class="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">{$_('auth.password')}</label>
                <input
                    id="password"
                    name="password"
                    bind:this={passwordInput}
                    aria-invalid={error ? 'true' : undefined}
                    aria-describedby={error ? 'login-error' : undefined}
                    type="password"
                    autocomplete="current-password"
                    required
                    bind:value={password}
                    class="input-base min-h-11"
                />
            </div>

            <!-- Always present, so the alert is announced the moment a message lands in it. -->
            <div id="login-error" role="alert" data-login-error>
                {#if error}
                    <p class="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm font-medium text-rose-800 dark:border-rose-900/60 dark:bg-rose-950/30 dark:text-rose-200">
                        {error}
                    </p>
                {/if}
            </div>

            <button type="submit" disabled={isLoading} aria-busy={isLoading} class="btn btn-primary min-h-11 w-full px-4">
                {#if isLoading}
                    <span class="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white motion-reduce:animate-none" aria-hidden="true"></span>
                    {$_('auth.verifying')}
                {:else}
                    {$_('auth.signin_button', { default: 'Sign in' })}
                {/if}
            </button>

            {#if authStore.publicAccessEnabled}
                <button type="button" onclick={() => authStore.cancelLogin()} class="btn btn-secondary min-h-11 w-full px-4">
                    {$_('auth.continue_guest', { default: 'Continue without signing in' })}
                </button>
            {/if}
        </form>
    </div>
</div>
