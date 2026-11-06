<script lang="ts">
    import AppearanceSettings from '../src/lib/components/settings/AppearanceSettings.svelte';
    import type { AppearanceDraft } from '../src/lib/settings/appearance-section';
    import type { Theme } from '../src/lib/stores/theme.svelte';
    let theme = $state<Theme>('light');
    let draft = $state<AppearanceDraft>({
        displayCommonNames: true,
        scientificNamePrimary: false,
        explorerView: 'cards',
        dateFormat: 'locale',
        timeFormat: 'locale',
        fontTheme: 'default',
        colorTheme: 'default'
    });
</script>
<AppearanceSettings
    currentTheme={theme}
    currentLocale="en"
    {draft}
    onchange={(patch) => (draft = { ...draft, ...patch })}
    setTheme={(next) => (theme = next)}
    setLanguage={() => undefined}
/>
