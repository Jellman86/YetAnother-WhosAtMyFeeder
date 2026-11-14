<script lang="ts">
    import { authStore } from '../stores/auth.svelte';
    import { _ } from 'svelte-i18n';
    import { APP_ICON_192_URL } from '../assets';
    import { signInFailure, type SignInFailure } from '../utils/sign-in-failure';

    let username = $state('');
    let password = $state('');
    let failure = $state<SignInFailure | null>(null);
    // Asked for once the form has been submitted, then kept honest as the fields are typed in.
    let submitted = $state(false);
    let isLoading = $state(false);
    let usernameInput = $state<HTMLInputElement | null>(null);
    let passwordInput = $state<HTMLInputElement | null>(null);

    const usernameMissing = $derived(submitted && !username.trim());
    const passwordMissing = $derived(submitted && !password);
    // Only a refused username and password pair is something the fields themselves can fix.
    const credentialsRefused = $derived(failure === 'wrong_credentials');

    const error = $derived.by(() => {
        switch (failure) {
            case 'wrong_credentials':
                return $_('auth.login_wrong_credentials', { default: 'That username or password is not right. Check both and try again. Passwords are case sensitive.' });
            case 'rate_limited':
                return $_('auth.login_rate_limited', { default: 'Too many sign-in attempts. Wait a minute, then try again.' });
            case 'unreachable':
                return $_('auth.login_unreachable', { default: 'Could not reach YA-WAMF. Check that it is running and that this device can reach it, then try again.' });
            case 'server':
                return $_('auth.login_server_error', { default: 'YA-WAMF could not check your sign-in. Try again in a moment. If it keeps happening, look at the container logs.' });
            default:
                return '';
        }
    });

    function describedBy(fieldMissing: boolean, fieldError: string): string | undefined {
        if (fieldMissing) return fieldError;
        return credentialsRefused ? 'login-error' : undefined;
    }

    async function handleSubmit(e: Event) {
        e.preventDefault();
        submitted = true;
        failure = null;
        if (!username.trim()) {
            usernameInput?.focus();
            return;
        }
        if (!password) {
            passwordInput?.focus();
            return;
        }

        isLoading = true;

        try {
            await authStore.login(username.trim(), password);
        } catch (err) {
            failure = signInFailure(err);
            isLoading = false;
            if (failure === 'wrong_credentials') {
                // The likeliest fix is retyping the password, so the cursor goes back there.
                passwordInput?.focus();
                passwordInput?.select();
            }
        }
    }
</script>

{#snippet fieldError(id: string, message: string)}
    <p {id} class="mt-1.5 flex items-start gap-1.5 text-sm font-medium text-rose-700 dark:text-rose-300" data-login-field-error>
        <svg class="mt-0.5 h-4 w-4 shrink-0" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10" cy="10" r="7.5" /><path stroke-linecap="round" d="M10 6v4.5m0 3v.01" /></svg>
        {message}
    </p>
{/snippet}

<main id="main-content" tabindex="-1" class="flex min-h-screen items-center justify-center px-4 py-10 focus:outline-hidden">
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

        <!-- Checked here, not by the browser: its "fill out this field" bubble names one field at a
             time, cannot be styled or translated by the app, and disappears on its own. -->
        <form class="space-y-5" onsubmit={handleSubmit} autocomplete="on" novalidate>
            <div>
                <label for="username" class="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">{$_('auth.username')}</label>
                <input
                    id="username"
                    name="username"
                    bind:this={usernameInput}
                    aria-invalid={usernameMissing || credentialsRefused ? 'true' : undefined}
                    aria-describedby={describedBy(usernameMissing, 'username-error')}
                    aria-required="true"
                    type="text"
                    autocomplete="username"
                    bind:value={username}
                    class="input-base min-h-11"
                    placeholder={$_('auth.username_placeholder')}
                />
                {#if usernameMissing}{@render fieldError('username-error', $_('auth.username_required', { default: 'Enter your username.' }))}{/if}
            </div>
            <div>
                <label for="password" class="mb-1.5 block text-sm font-medium text-slate-700 dark:text-slate-300">{$_('auth.password')}</label>
                <input
                    id="password"
                    name="password"
                    bind:this={passwordInput}
                    aria-invalid={passwordMissing || credentialsRefused ? 'true' : undefined}
                    aria-describedby={describedBy(passwordMissing, 'password-error')}
                    aria-required="true"
                    type="password"
                    autocomplete="current-password"
                    bind:value={password}
                    class="input-base min-h-11"
                />
                {#if passwordMissing}{@render fieldError('password-error', $_('auth.password_required', { default: 'Enter your password.' }))}{/if}
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
</main>
