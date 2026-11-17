<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { get } from 'svelte/store';
    import { authStore } from '../../stores/auth.svelte';
    import { setupWizardStore } from '../../stores/setup_wizard.svelte';
    import { AUTH_PASSWORD_REQUIREMENTS, passwordProblemMessage, validateAuthPasswordPolicy } from '../../auth-password-policy';
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
            setupWizardStore.completeStep();
            return;
        }
        if (!skipAuth) {
            if (password !== confirmPassword) {
                error = get(_)('first_run.password_mismatch', { default: "Passwords don't match" });
                return;
            }
            const problem = validateAuthPasswordPolicy(password);
            if (problem) {
                const message = passwordProblemMessage(problem);
                error = get(_)(message.key, { default: message.default });
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
            setupWizardStore.completeStep();
        } catch (err) {
            error = err instanceof Error ? err.message : get(_)('first_run.setup_failed', { default: 'The password could not be saved. Check that YA-WAMF is running, then try again.' });
        } finally {
            busy = false;
        }
    }
</script>

<WizardStepLayout
    title={$_('setup.account.title', { default: 'Owner account and access' })}
    description={$_('setup.account.description', {
        default: 'Protect the dashboard with an owner password, or run without authentication on a trusted network.'
    })}
    {busy}
    onContinue={save}
>
    {#if alreadyConfigured}
        <div class="rounded-md bg-accent-soft p-3 text-sm text-accent-ink">
            {$_('setup.account.already', { default: 'Authentication is already configured. Manage it in Settings → Sharing & integrations.' })}
        </div>
    {:else}
        {#if !skipAuth}
            <div>
                <label for="setup-username" class="text-sm font-medium text-ink">{$_('first_run.admin_username', { default: 'Owner user name' })}</label>
                <input id="setup-username" type="text" autocomplete="username" bind:value={username} class="input-base mt-1" />
            </div>
            <div>
                <label for="setup-password" class="text-sm font-medium text-ink">{$_('first_run.password', { default: 'Password' })}</label>
                <input id="setup-password" type="password" minlength="8" autocomplete="new-password" aria-describedby="setup-password-rules" bind:value={password} class="input-base mt-1" />
                <p id="setup-password-rules" class="mt-1 text-xs text-muted">
                    {$_(AUTH_PASSWORD_REQUIREMENTS.key, { default: AUTH_PASSWORD_REQUIREMENTS.default })}
                </p>
            </div>
            <div>
                <label for="setup-confirm" class="text-sm font-medium text-ink">{$_('first_run.confirm_password', { default: 'Confirm password' })}</label>
                <input id="setup-confirm" type="password" minlength="8" autocomplete="new-password" aria-describedby="setup-password-rules" bind:value={confirmPassword} class="input-base mt-1" />
            </div>
        {/if}

        {#if error}
            <div role="alert" class="rounded-md bg-status-fail-soft p-3 text-sm text-status-fail">{error}</div>
        {/if}

        <label class="flex min-h-11 items-center gap-2 text-sm text-ink">
            <input type="checkbox" bind:checked={skipAuth} class="rounded-sm border-line-strong text-accent focus:ring-focus" />
            {$_('first_run.skip_auth', { default: 'Run without a password (trusted network only)' })}
        </label>
    {/if}
</WizardStepLayout>
