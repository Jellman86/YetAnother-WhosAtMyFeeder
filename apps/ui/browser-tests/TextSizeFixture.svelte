<script lang="ts">
    import AppearanceSettings from '../src/lib/components/settings/AppearanceSettings.svelte';
    import type { ColorTheme, FontTheme, Theme } from '../src/lib/stores/theme.svelte';
    let theme = $state<Theme>('light');
    let font = $state<FontTheme>('default');
    let colour = $state<ColorTheme>('default');
</script>
<AppearanceSettings
    currentTheme={theme}
    currentLocale="en"
    currentDateFormat="locale"
    currentTimeFormat="locale"
    setTheme={(next) => (theme = next)}
    setLanguage={() => undefined}
    currentFontTheme={font}
    setFontTheme={(next) => (font = next)}
    currentColorTheme={colour}
    setColorTheme={(next) => (colour = next)}
    setDateFormat={() => undefined}
    setTimeFormat={() => undefined}
    displayCommonNames={true}
    scientificNamePrimary={false}
    explorerView="cards"
/>
