<script lang="ts">
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type { Theme } from '../../../stores/theme.svelte';
    import type { AppearanceDraft } from '../../../settings/appearance-section';
    import type { AccessibilityDraft } from '../../../settings/accessibility-section';
    import type { WeatherUnitSystem } from '../../../utils/weather-units';
    import { loadAccessibilitySettings, loadAppearanceSettings, loadUnitsSettings } from './part-loaders';
    import SectionMore from './SectionMore.svelte';

    // Display: theme, text size, language and accessibility first; dates, names, the Explorer
    // layout, fonts and colours, and units under More options. Holds what were the Appearance and
    // Accessibility tabs.
    interface Props {
        currentTheme: Theme;
        currentLocale: string;
        appearanceDraft: AppearanceDraft;
        onAppearanceChange: (patch: Partial<AppearanceDraft>) => void;
        setTheme: (theme: Theme) => void;
        setLanguage: (language: string) => Promise<void>;
        accessibilityDraft: AccessibilityDraft;
        onAccessibilityChange: (patch: Partial<AccessibilityDraft>) => void;
        locationWeatherUnitSystem: WeatherUnitSystem;
    }

    let {
        currentTheme,
        currentLocale,
        appearanceDraft,
        onAppearanceChange,
        setTheme,
        setLanguage,
        accessibilityDraft,
        onAccessibilityChange,
        locationWeatherUnitSystem = $bindable()
    }: Props = $props();
</script>

<div class="space-y-8" data-settings-section="display">
    <div class="space-y-8" data-settings-part="appearance">
        <LazyRoute
            loader={loadAppearanceSettings}
            label={$_('settings.tabs.appearance')}
            props={{
                region: 'main',
                currentTheme,
                currentLocale,
                draft: appearanceDraft,
                onchange: onAppearanceChange,
                setTheme,
                setLanguage
            }}
        />
    </div>

    <div class="space-y-8" data-settings-part="accessibility">
        <LazyRoute
            loader={loadAccessibilitySettings}
            label={$_('settings.tabs.accessibility')}
            props={{
                draft: accessibilityDraft,
                onchange: onAccessibilityChange
            }}
        />
    </div>

    <SectionMore section="display" summary={$_('settings.more.display', { default: 'Date and time format, how birds are named, the Explorer layout, fonts and colours, and units' })}>
        <LazyRoute
            loader={loadAppearanceSettings}
            label={$_('settings.tabs.appearance')}
            props={{
                region: 'more',
                currentTheme,
                currentLocale,
                draft: appearanceDraft,
                onchange: onAppearanceChange,
                setTheme,
                setLanguage
            }}
        />
        <!-- Units are how numbers read, so they sit with the rest of how YA-WAMF looks; they are
             saved for everyone, which the card says. -->
        <LazyRoute loader={loadUnitsSettings} label={$_('settings.units.title', { default: 'Units' })}>
        {#snippet content(UnitsSettings)}
        <UnitsSettings bind:locationWeatherUnitSystem />
        {/snippet}
        </LazyRoute>
    </SectionMore>
</div>
