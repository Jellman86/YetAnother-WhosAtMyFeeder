<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { Theme, FontTheme, ColorTheme } from '../../stores/theme.svelte';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsSelect from './_primitives/SettingsSelect.svelte';
    import SettingsSegmented from './_primitives/SettingsSegmented.svelte';
    import AdvancedSection from './_primitives/AdvancedSection.svelte';
    import { themeStore, TEXT_SIZE_SCALE, type TextSize } from '../../stores/theme.svelte';

    let {
        currentTheme,
        currentLocale,
        currentDateFormat,
        currentTimeFormat,
        setTheme,
        setLanguage,
        currentFontTheme,
        setFontTheme,
        currentColorTheme,
        setColorTheme,
        setDateFormat,
        setTimeFormat,
        displayCommonNames = $bindable(true),
        scientificNamePrimary = $bindable(false),
        explorerView = $bindable<'cards' | 'list'>('cards')
    }: {
        currentTheme: Theme;
        currentLocale: string;
        currentDateFormat: string;
        currentTimeFormat: string;
        setTheme: (theme: Theme) => void;
        setLanguage: (lang: string) => void | Promise<void>;
        currentFontTheme: FontTheme;
        setFontTheme: (font: FontTheme) => void;
        currentColorTheme: ColorTheme;
        setColorTheme: (color: ColorTheme) => void;
        setDateFormat: (format: string) => void;
        setTimeFormat: (format: string) => void;
        displayCommonNames: boolean;
        scientificNamePrimary: boolean;
        explorerView: 'cards' | 'list';
    } = $props();

    // Each choice previews itself: the "Aa" grows step by step, on the constrained type scale.
    const TEXT_SIZES: { value: TextSize; sample: string }[] = [
        { value: 'smaller', sample: 'text-base' },
        { value: 'standard', sample: 'text-lg' },
        { value: 'large', sample: 'text-xl' },
        { value: 'larger', sample: 'text-2xl' },
        { value: 'largest', sample: 'text-3xl' }
    ];

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
        labelId="setting-text-size"
        label={$_('settings.text_size.label', { default: 'Text size' })}
        description={$_('settings.text_size.desc', { default: 'Makes every page larger or smaller on this device only. Large displays still grow a little on top of it.' })}
        layout="stacked"
    >
        <!-- Wraps by its own size, so the largest text still leaves each choice room on a phone. -->
        <div class="grid grid-cols-[repeat(auto-fit,minmax(4rem,1fr))] gap-2" role="group" aria-labelledby="setting-text-size" data-text-size-options>
            {#each TEXT_SIZES as size (size.value)}
                {@const active = themeStore.textSize === size.value}
                {@const name = $_(`settings.text_size.${size.value}`)}
                <button
                    type="button"
                    aria-pressed={active}
                    aria-label={$_('settings.text_size.option', { values: { size: name, percent: Math.round(TEXT_SIZE_SCALE[size.value] * 100) }, default: '{size}, {percent}%' })}
                    onclick={() => themeStore.setTextSize(size.value)}
                    class="flex min-h-16 min-w-0 flex-col items-center justify-end gap-1.5 rounded-2xl border-2 px-1 pb-2.5 pt-2 transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-brand-400 {active
                        ? 'border-brand-500 bg-brand-500 text-white shadow-lg shadow-brand-500/20'
                        : 'border-slate-100 bg-white text-slate-700 hover:border-brand-500/30 dark:border-slate-700/50 dark:bg-slate-900/50 dark:text-slate-200'}"
                    data-text-size={size.value}
                >
                    <span class="font-display font-bold leading-none {size.sample}" aria-hidden="true">Aa</span>
                    <span class="max-w-full break-words text-center text-xs font-semibold leading-tight">{name}</span>
                </button>
            {/each}
        </div>
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
            value={explorerView}
            ariaLabel={$_('settings.explorer_view.label')}
            onchange={(v) => (explorerView = v as 'cards' | 'list')}
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
            value={currentDateFormat}
            ariaLabel={$_('settings.date_format.label')}
            onchange={(v) => setDateFormat(v)}
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
            value={currentTimeFormat}
            ariaLabel={$_('settings.time_format.label')}
            onchange={(v) => setTimeFormat(v)}
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
                    { value: 'default', label: $_('theme.color_default'), sub: $_('theme.color_default_desc'), swatch: 'bg-brand-500' },
                    { value: 'bluetit', label: $_('theme.color_bluetit'), sub: $_('theme.color_bluetit_desc'), swatch: 'bg-gradient-to-br from-blue-500 to-amber-400' }
                ]}
            />
        </SettingsRow>
    </AdvancedSection>
</SettingsCard>
