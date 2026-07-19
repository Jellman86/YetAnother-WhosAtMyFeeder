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

    const covers = [
        { icon: '🔗', label: $_('setup.welcome.cover_connect', { default: 'Connect Frigate & MQTT' }) },
        { icon: '📷', label: $_('setup.welcome.cover_cameras', { default: 'Pick your cameras' }) },
        { icon: '🧠', label: $_('setup.welcome.cover_model', { default: 'Validate the model on your hardware' }) },
        { icon: '🧩', label: $_('setup.welcome.cover_integrations', { default: 'Turn on integrations' }) }
    ];
</script>

<WizardStepLayout
    title={$_('setup.welcome.title', { default: 'Welcome to YA-WAMF' })}
    description={$_('setup.welcome.description', {
        default: "Let's get your feeder online. This takes a few minutes, every step is optional, and you can re-run this setup any time from Settings."
    })}
    showBack={false}
    continueLabel={$_('setup.welcome.start', { default: 'Get started' })}
>
    <div class="grid grid-cols-2 gap-2">
        {#each covers as item}
            <div class="flex items-center gap-2 rounded-xl border border-slate-200 bg-slate-50/60 px-3 py-2.5 text-sm text-slate-700 dark:border-slate-700 dark:bg-slate-800/40 dark:text-slate-200">
                <span aria-hidden="true">{item.icon}</span>
                <span>{item.label}</span>
            </div>
        {/each}
    </div>

    <div class="space-y-2">
        <label for="setup-language" class="text-sm font-medium text-slate-700 dark:text-slate-300">
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
        <p class="text-xs text-slate-500 dark:text-slate-400">
            {$_('first_run.language_desc', { default: 'You can change this later in Settings.' })}
        </p>
        {#if languageError}
            <p class="text-xs font-medium text-amber-700 dark:text-amber-300" role="alert">
                {$_('common.language_load_error', { default: 'That language could not be loaded. Check your connection and try again.' })}
            </p>
        {/if}
    </div>
</WizardStepLayout>
