<script lang="ts">
    import { authStore } from '../stores/auth.svelte';
    import { _, locale } from 'svelte-i18n';
    import { get } from 'svelte/store';

    let username = $state('admin');
    let password = $state('');
    let confirmPassword = $state('');
    let skipAuth = $state(false);
    let isLoading = $state(false);
    let error = $state<string | null>(null);

    const supportedLocales = [
        { value: 'en', label: 'English' },
        { value: 'es', label: 'Español' },
        { value: 'fr', label: 'Français' },
        { value: 'de', label: 'Deutsch' },
        { value: 'ja', label: '日本語' },
        { value: 'zh', label: '中文' },
        { value: 'ru', label: 'Русский' },
        { value: 'pt', label: 'Português' },
        { value: 'it', label: 'Italiano' }
    ];

    function setLanguage(lang: string) {
        locale.set(lang);
        localStorage.setItem('preferred-language', lang);
    }

    async function handleSubmit(e: Event) {
        e.preventDefault();
        error = null;

        if (!skipAuth) {
            if (password !== confirmPassword) {
                error = get(_)('first_run.password_mismatch', { default: "Passwords don't match" });
                return;
            }
            if (password.length < 8) {
                error = get(_)('first_run.password_min', { default: 'Password must be at least 8 characters' });
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
            error = err instanceof Error
                ? err.message
                : get(_)('first_run.setup_failed', { default: 'Setup failed' });
        } finally {
            isLoading = false;
        }
    }
</script>

<div class="min-h-screen flex items-center justify-center bg-surface-50 dark:bg-surface-900 px-4">
    <div class="max-w-lg w-full space-y-8 bg-white dark:bg-surface-800 p-8 rounded-xl shadow-lg border border-surface-200 dark:border-surface-700">
        <div class="text-center space-y-2">
            <h1 class="text-3xl font-bold text-gray-900 dark:text-white">{$_('first_run.title')}</h1>
            <p class="text-sm text-gray-600 dark:text-gray-400">
                {$_('first_run.subtitle')}
            </p>
        </div>

        <div class="space-y-2">
            <label for="language-select" class="text-sm font-medium text-gray-700 dark:text-gray-300">
                {$_('first_run.language_label')}
            </label>
            <select
                id="language-select"
                value={$locale}
                onchange={(e) => setLanguage(e.currentTarget.value)}
                aria-label="{$_('first_run.language_label')}"
                class="input-base"
            >
                {#each supportedLocales as localeOption}
                    <option value={localeOption.value}>{localeOption.label}</option>
                {/each}
            </select>
            <p class="text-xs text-gray-500 dark:text-gray-400">
                {$_('first_run.language_desc')}
            </p>
        </div>

        <form class="space-y-6" onsubmit={handleSubmit}>
            {#if !skipAuth}
                <div>
                    <label for="username" class="text-sm font-medium text-gray-700 dark:text-gray-300">{$_('first_run.admin_username')}</label>
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
                    <label for="password" class="text-sm font-medium text-gray-700 dark:text-gray-300">{$_('first_run.password')}</label>
                    <input
                        id="password"
                        name="password"
                        type="password"
                        required
                        minlength="8"
                        bind:value={password}
                        class="input-base mt-1"
                    />
                    <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">{$_('first_run.password_hint')}</p>
                </div>

                <div>
                    <label for="confirm-password" class="text-sm font-medium text-gray-700 dark:text-gray-300">{$_('first_run.confirm_password')}</label>
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
                {$_('first_run.skip_auth')}
            </label>

            <button
                type="submit"
                disabled={isLoading}
                class="btn btn-primary w-full py-3"
            >
                {#if isLoading}
                    {$_('first_run.setting_up')}
                {:else}
                    {#if skipAuth}
                        {$_('first_run.continue_without_password')}
                    {:else}
                        {$_('first_run.set_password')}
                    {/if}
                {/if}
            </button>
        </form>
    </div>
</div>
