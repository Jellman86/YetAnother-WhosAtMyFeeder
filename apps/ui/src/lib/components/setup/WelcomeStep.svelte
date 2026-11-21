<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import WizardStepLayout from './WizardStepLayout.svelte';
    import { setAppLocale } from '../../i18n';

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

    let languageChanging = $state(false);
    let languageError = $state(false);

    async function setLanguage(lang: string): Promise<void> {
        if (languageChanging) return;
        languageChanging = true;
        languageError = !(await setAppLocale(lang));
        languageChanging = false;
    }

    let covers = $derived([
        { id: 'connection', label: $_('setup.welcome.cover_connect', { default: 'Connect Frigate & MQTT' }) },
        { id: 'cameras', label: $_('setup.welcome.cover_cameras', { default: 'Pick your cameras' }) },
        { id: 'model', label: $_('setup.welcome.cover_model', { default: 'Check the model runs on this machine' }) },
        { id: 'integrations', label: $_('setup.welcome.cover_integrations', { default: 'Turn on integrations' }) }
    ]);
</script>

<WizardStepLayout
    title={$_('setup.welcome.title', { default: 'Set up YA-WAMF' })}
    description={$_('setup.welcome.description', {
        default: 'This takes a few minutes. Optional choices can be skipped, and you can run setup again at any time from Settings.'
    })}
    showBack={false}
    continueLabel={$_('setup.welcome.start', { default: 'Get started' })}
>
    <!-- What setup will ask for, as a plain list: tiles here looked like buttons and did nothing. -->
    <div>
        <p class="text-sm font-semibold text-strong">{$_('setup.welcome.covers', { default: 'Setup will ask you to:' })}</p>
        <ul class="mt-1 list-disc space-y-1 pl-5 text-sm text-ink" data-setup-welcome-covers>
            {#each covers as item (item.id)}
                <li>{item.label}</li>
            {/each}
        </ul>
    </div>

    <div class="space-y-2">
        <label for="setup-language" class="text-sm font-medium text-ink">
            {$_('first_run.language_label', { default: 'Language' })}
        </label>
        <select
            id="setup-language"
            value={$locale}
            onchange={(e) => setLanguage(e.currentTarget.value)}
            disabled={languageChanging}
            class="select-base"
        >
            {#each supportedLocales as opt}
                <option value={opt.value}>{opt.label}</option>
            {/each}
        </select>
        <p class="text-xs text-muted">
            {$_('first_run.language_desc', { default: 'You can change this later in Settings.' })}
        </p>
        {#if languageError}
            <p class="text-xs font-medium text-status-attention" role="alert">
                {$_('common.language_load_error', { default: 'That language could not be loaded. Check your connection and try again.' })}
            </p>
        {/if}
    </div>
</WizardStepLayout>
