<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Theme, FontTheme, ColorTheme } from '../../stores/theme.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';

    let {
        currentTheme,
        currentLocale,
        currentDateFormat,
        setTheme,
        setLanguage,
        currentFontTheme,
        setFontTheme,
        currentColorTheme,
        setColorTheme,
        setDateFormat,
        displayCommonNames = $bindable(true),
        scientificNamePrimary = $bindable(false)
    }: {
        currentTheme: Theme;
        currentLocale: string;
        currentDateFormat: string;
        setTheme: (theme: Theme) => void;
        setLanguage: (lang: string) => void;
        currentFontTheme: FontTheme;
        setFontTheme: (font: FontTheme) => void;
        currentColorTheme: ColorTheme;
        setColorTheme: (color: ColorTheme) => void;
        setDateFormat: (format: string) => void;
        displayCommonNames: boolean;
        scientificNamePrimary: boolean;
    } = $props();

    type NamingMode = 'standard' | 'hobbyist' | 'scientific';

    const currentNamingMode: NamingMode = $derived(
        !displayCommonNames ? 'scientific' : scientificNamePrimary ? 'hobbyist' : 'standard'
    );

    function setNamingMode(mode: NamingMode) {
        if (mode === 'scientific') {
            displayCommonNames = false;
            scientificNamePrimary = false;
            return;
        }
        displayCommonNames = true;
        scientificNamePrimary = mode === 'hobbyist';
    }
</script>

{#snippet appearanceIcon()}
    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 3v2m0 14v2M3 12h2m14 0h2M5.64 5.64l1.42 1.42m9.88 9.88 1.42 1.42m0-12.72-1.42 1.42M7.06 16.94l-1.42 1.42M16 12a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z" /></svg>
{/snippet}

<SettingsCard accent iconSnippet={appearanceIcon} title={$_('theme.title')}>
    <SettingsRow
        labelId="setting-theme"
        label={$_('theme.title')}
        layout="stacked"
    >
        <SettingsSegmented
            value={currentTheme}
            ariaLabelTemplate={(label) => $_('theme.select', { values: { theme: label } })}
            onchange={(v) => setTheme(v as Theme)}
            options={[
                { value: 'light', label: $_('theme.light') },
                { value: 'dark', label: $_('theme.dark') },
                { value: 'system', label: $_('theme.system') }
            ]}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-language"
        label={$_('settings.language_selector')}
        description={$_('settings.language_desc')}
        layout="stacked"
    >
        <SettingsSelect
            id="language-select"
            value={currentLocale}
            ariaLabel={$_('settings.language_selector')}
            onchange={(v) => setLanguage(v)}
            options={[
                { value: 'en', label: 'English' },
                { value: 'es', label: 'Español' },
                { value: 'fr', label: 'Français' },
                { value: 'de', label: 'Deutsch' },
                { value: 'ja', label: '日本語' },
                { value: 'zh', label: '中文' },
                { value: 'ru', label: 'Русский' },
                { value: 'pt', label: 'Português' },
                { value: 'it', label: 'Italiano' }
            ]}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-date-format"
        label={$_('settings.date_format.label')}
        description={$_('settings.date_format.desc')}
        layout="stacked"
    >
        <SettingsSelect
            id="date-format-select"
            value={currentDateFormat}
            ariaLabel={$_('settings.date_format.label')}
            onchange={(v) => setDateFormat(v)}
            options={[
                { value: 'mdy', label: $_('settings.date_format.us') },
                { value: 'dmy', label: $_('settings.date_format.uk') },
                { value: 'ymd', label: $_('settings.date_format.ymd') }
            ]}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-naming"
        label={$_('settings.detection.naming_title')}
        layout="stacked"
    >
        <SettingsSegmented
            value={currentNamingMode}
            layout="card"
            columns={1}
            ariaLabelTemplate={(label) => $_('settings.detection.naming_select_label', { values: { mode: label } })}
            onchange={(v) => setNamingMode(v as NamingMode)}
            options={[
                { value: 'standard', label: $_('settings.detection.naming_standard'), sub: $_('settings.detection.naming_standard_sub') },
                { value: 'hobbyist', label: $_('settings.detection.naming_hobbyist'), sub: $_('settings.detection.naming_hobbyist_sub') },
                { value: 'scientific', label: $_('settings.detection.naming_scientific'), sub: $_('settings.detection.naming_scientific_sub') }
            ]}
        />
    </SettingsRow>

    <AdvancedSection
        id="appearance-typography-and-colour"
        title={$_('settings.common.advanced_default_title', { default: 'Advanced options' })}
    >
        <SettingsRow
            labelId="setting-font-theme"
            label={$_('theme.font_title')}
            description={$_('theme.font_desc')}
            layout="stacked"
        >
            <SettingsSegmented
                value={currentFontTheme}
                layout="card"
                ariaLabelTemplate={(label) => label}
                onchange={(v) => setFontTheme(v as FontTheme)}
                options={[
                    { value: 'default', label: $_('theme.font_default'), sub: 'Instrument Sans / Bricolage', meta: $_('theme.font_lang_default') },
                    { value: 'clean', label: $_('theme.font_clean'), sub: 'Manrope / Sora', meta: $_('theme.font_lang_clean') },
                    { value: 'studio', label: $_('theme.font_studio'), sub: 'Sora / Bricolage', meta: $_('theme.font_lang_studio') },
                    { value: 'classic', label: $_('theme.font_classic'), sub: 'Source Serif 4 / Playfair', meta: $_('theme.font_lang_classic') },
                    { value: 'compact', label: $_('theme.font_compact'), sub: 'Instrument Sans / Sora', meta: $_('theme.font_lang_compact') }
                ]}
            />
        </SettingsRow>

        <SettingsRow
            labelId="setting-color-theme"
            label={$_('theme.color_title')}
            description={$_('theme.color_desc')}
            layout="stacked"
        >
            <SettingsSegmented
                value={currentColorTheme}
                layout="card"
                ariaLabelTemplate={(label) => label}
                onchange={(v) => setColorTheme(v as ColorTheme)}
                options={[
                    { value: 'default', label: $_('theme.color_default'), sub: $_('theme.color_default_desc'), swatch: 'bg-teal-500' },
                    { value: 'bluetit', label: $_('theme.color_bluetit'), sub: $_('theme.color_bluetit_desc'), swatch: 'bg-gradient-to-br from-blue-500 to-amber-400' }
                ]}
            />
        </SettingsRow>
    </AdvancedSection>
</SettingsCard>
