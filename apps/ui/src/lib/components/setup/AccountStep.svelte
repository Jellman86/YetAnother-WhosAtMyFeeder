<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import { authStore } from '../../stores/auth.svelte';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { AUTH_PASSWORD_REQUIREMENTS_MESSAGE, validateAuthPasswordPolicy } from '../../auth-password-policy';
    import WizardStepLayout from './WizardStepLayout.svelte';

    let alreadyConfigured = $derived(!authStore.needsInitialSetup);

    let username = $state('admin');
    let password = $state('');
    let confirmPassword = $state('');
    let skipAuth = $state(false);
    let busy = $state(false);
    let error = $state<string | null>(null);

    async function save() {
        error = null;
        if (alreadyConfigured) {
            setupWizardStore.next();
            return;
        }
        if (!skipAuth) {
            if (password !== confirmPassword) {
                error = get(_)('first_run.password_mismatch', { default: "Passwords don't match" });
                return;
            }
            const policyError = validateAuthPasswordPolicy(password);
            if (policyError) {
                error = policyError;
                return;
            }
        }
        busy = true;
        try {
            await authStore.completeInitialSetup({
                username: username.trim() || 'admin',
                password: skipAuth ? null : password,
                enableAuth: !skipAuth
            });
            await setupWizardStore.refresh();
            setupWizardStore.next();
        } catch (err) {
            error = err instanceof Error ? err.message : get(_)('first_run.setup_failed', { default: 'Setup failed' });
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.account.title', { default: 'Admin account & access' })}
    description={$_('setup.account.description', {
        default: 'Protect the dashboard with an owner password, or run without authentication on a trusted network.'
    })}
    {busy}
    onContinue={save}
>
    {#if alreadyConfigured}
        <div class="rounded-md bg-accent-50 p-3 text-sm text-accent-800 dark:bg-accent-900/20 dark:text-accent-200">
            {$_('setup.account.already', { default: 'Authentication is already configured. Manage it in Settings → Security.' })}
        </div>
    {:else}
        {#if !skipAuth}
            <div>
                <label for="setup-username" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('first_run.admin_username', { default: 'Admin username' })}</label>
                <input id="setup-username" type="text" bind:value={username} class="input-base mt-1" />
            </div>
            <div>
                <label for="setup-password" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('first_run.password', { default: 'Password' })}</label>
                <input id="setup-password" type="password" minlength="8" bind:value={password} class="input-base mt-1" />
                <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">{AUTH_PASSWORD_REQUIREMENTS_MESSAGE}</p>
            </div>
            <div>
                <label for="setup-confirm" class="text-sm font-medium text-slate-700 dark:text-slate-300">{$_('first_run.confirm_password', { default: 'Confirm password' })}</label>
                <input id="setup-confirm" type="password" minlength="8" bind:value={confirmPassword} class="input-base mt-1" />
            </div>
        {/if}

        {#if error}
            <div role="alert" class="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-900/20 dark:text-red-200">{error}</div>
        {/if}

        <label class="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300">
            <input type="checkbox" bind:checked={skipAuth} class="rounded border-slate-300 text-brand-600 focus:ring-brand-500" />
            {$_('first_run.skip_auth', { default: 'Run without a password (trusted network only)' })}
        </label>
    {/if}
</WizardStepLayout>
