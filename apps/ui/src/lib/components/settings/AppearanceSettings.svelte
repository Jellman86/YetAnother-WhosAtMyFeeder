<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Theme, FontTheme, ColorTheme } from '../../stores/theme.svelte';
    import type { AppearanceDraft, ExplorerView } from '../../settings/appearance-section';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import { themeStore, type TextSize } from '../../stores/theme.svelte';

    let {
        currentTheme,
        currentLocale,
        draft,
        onchange,
        setTheme,
        setLanguage
    }: {
        currentTheme: Theme;
        currentLocale: string;
        /** The saved-for-everyone Appearance choices as currently edited; Apply saves them. */
        draft: AppearanceDraft;
        onchange: (patch: Partial<AppearanceDraft>) => void;
        setTheme: (theme: Theme) => void;
        setLanguage: (lang: string) => void | Promise<void>;
    } = $props();

    // Smallest to largest, as the select lists them.
    const TEXT_SIZES: readonly TextSize[] = ['smallest', 'smaller', 'standard', 'large', 'larger', 'extra_large', 'largest'];

    type NamingMode = 'standard' | 'hobbyist' | 'scientific';

    const currentNamingMode: NamingMode = $derived(
        !draft.displayCommonNames ? 'scientific' : draft.scientificNamePrimary ? 'hobbyist' : 'standard'
    );

    function setNamingMode(mode: NamingMode) {
        if (mode === 'scientific') {
            onchange({ displayCommonNames: false, scientificNamePrimary: false });
            return;
        }
        onchange({ displayCommonNames: true, scientificNamePrimary: mode === 'hobbyist' });
    }
</script>


<SettingsCard title={$_('settings.tabs.appearance')} description={$_('settings.appearance.scope', { default: 'Theme, text size and language change at once on this device. The rest apply to everyone who uses this install once you save.' })}>
    <SettingsRow
        labelId="setting-theme"
        label={$_('theme.title')}
        description={$_('settings.theme_scope', { default: 'Changes at once, on this device only.' })}
        layout="stacked"
    >
        <SettingsSegmented
            value={currentTheme}
            labelledBy="setting-theme"
            onchange={(v) => setTheme(v as Theme)}
            options={[
                { value: 'light', label: $_('theme.light') },
                { value: 'dark', label: $_('theme.dark') },
                { value: 'system', label: $_('theme.system') }
            ]}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-text-size"
        label={$_('settings.text_size.label', { default: 'Text size' })}
        description={$_('settings.text_size.desc', { default: 'Makes every page larger or smaller on this device only. Large displays still grow a little on top of it.' })}
        layout="stacked"
    >
        <!-- Seven sizes do not fit on one line, so they are a select; the page itself is the preview. -->
        <select
            id="text-size"
            class="select-base min-h-11 w-full"
            aria-labelledby="setting-text-size"
            value={themeStore.textSize}
            onchange={(event) => {
                const chosen = TEXT_SIZES.find((size) => size === (event.currentTarget as HTMLSelectElement).value);
                if (chosen) themeStore.setTextSize(chosen);
            }}
            data-text-size-options
        >
            {#each TEXT_SIZES as size (size)}
                <option value={size}>{$_(`settings.text_size.${size}`)}</option>
            {/each}
        </select>
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
            onchange={(v) => void setLanguage(v)}
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
        labelId="setting-explorer-view"
        label={$_('settings.explorer_view.label')}
        description={$_('settings.explorer_view.desc')}
        layout="stacked"
    >
        <SettingsSelect
            id="explorer-view-select"
            value={draft.explorerView}
            ariaLabel={$_('settings.explorer_view.label')}
            onchange={(v) => onchange({ explorerView: v as ExplorerView })}
            options={[
                { value: 'cards', label: $_('settings.explorer_view.cards') },
                { value: 'list', label: $_('settings.explorer_view.list') }
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
            value={draft.dateFormat}
            ariaLabel={$_('settings.date_format.label')}
            onchange={(v) => onchange({ dateFormat: v as AppearanceDraft['dateFormat'] })}
            options={[
                { value: 'locale', label: $_('settings.date_format.locale', { default: 'Follow browser language' }) },
                { value: 'mdy', label: $_('settings.date_format.us') },
                { value: 'dmy', label: $_('settings.date_format.uk') },
                { value: 'ymd', label: $_('settings.date_format.ymd') }
            ]}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-time-format"
        label={$_('settings.time_format.label')}
        description={$_('settings.time_format.desc')}
        layout="stacked"
    >
        <SettingsSelect
            id="time-format-select"
            value={draft.timeFormat}
            ariaLabel={$_('settings.time_format.label')}
            onchange={(v) => onchange({ timeFormat: v as AppearanceDraft['timeFormat'] })}
            options={[
                { value: 'locale', label: $_('settings.time_format.locale') },
                { value: '12h', label: $_('settings.time_format.h12') },
                { value: '24h', label: $_('settings.time_format.h24') }
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
            labelledBy="setting-naming"
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
        title={$_('settings.appearance.typography_title', { default: 'Fonts and colours' })}
    >
        <SettingsRow
            labelId="setting-font-theme"
            label={$_('theme.font_title')}
            description={$_('theme.font_desc')}
            layout="stacked"
        >
            <SettingsSegmented
                value={draft.fontTheme}
                layout="card"
                labelledBy="setting-font-theme"
                onchange={(v) => onchange({ fontTheme: v as FontTheme })}
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
                value={draft.colorTheme}
                layout="card"
                labelledBy="setting-color-theme"
                onchange={(v) => onchange({ colorTheme: v as ColorTheme })}
                options={[
                    { value: 'default', label: $_('theme.color_default'), sub: $_('theme.color_default_desc'), swatch: 'bg-brand-500' },
                    { value: 'bluetit', label: $_('theme.color_bluetit'), sub: $_('theme.color_bluetit_desc'), swatch: 'bg-linear-to-br/srgb from-blue-500 to-amber-400' }
                ]}
            />
        </SettingsRow>
    </AdvancedSection>
</SettingsCard>
