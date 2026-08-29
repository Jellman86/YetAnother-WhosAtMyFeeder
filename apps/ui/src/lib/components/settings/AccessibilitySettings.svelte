<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import { accessibilityPreview } from '../../stores/accessibility_preview.svelte';

    let {
        highContrast = $bindable(false),
        dyslexiaFont = $bindable(false),
        liveAnnouncements = $bindable(true),
        reducedMotion = $bindable(false)
    }: {
        highContrast: boolean;
        dyslexiaFont: boolean;
        liveAnnouncements: boolean;
        reducedMotion: boolean;
    } = $props();

    // OpenDyslexic font only supports Latin characters
    const latinLanguages = ['en', 'es', 'fr', 'de'];
    const currentLocale = $derived(typeof $locale === 'string' ? $locale : 'en');
    const showDyslexicFont = $derived(latinLanguages.includes(currentLocale));

    // The document root has exactly one owner: App.svelte applies
    // preview ?? saved. Publishing only on a change (never on mount) means
    // opening this tab cannot strip a saved-on class while settings are
    // still loading, and clearing on unmount means an abandoned preview
    // falls back to the saved value instead of sticking until a reload.
    $effect(() => {
        return () => accessibilityPreview.clear();
    });
</script>

{#snippet accessibilityIcon()}
    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="4" r="2" /><path d="M4 9h16m-8 0v12m0-7-4 7m4-7 4 7" /></svg>
{/snippet}

<SettingsCard accent iconSnippet={accessibilityIcon} title={$_('settings.accessibility.title')}>
    <SettingsRow
        labelId="setting-high-contrast"
        label={$_('settings.accessibility.high_contrast')}
        description={$_('settings.accessibility.high_contrast_desc')}
    >
        <SettingsToggle
            checked={highContrast}
            labelledBy="setting-high-contrast"
            srLabel={$_('settings.accessibility.high_contrast')}
            onchange={(v) => {
                highContrast = v;
                accessibilityPreview.highContrast = v;
            }}
        />
    </SettingsRow>

    {#if showDyslexicFont}
        <SettingsRow
            labelId="setting-dyslexia-font"
            label={$_('settings.accessibility.dyslexia_font')}
            description={$_('settings.accessibility.dyslexia_font_desc')}
        >
            <SettingsToggle
                checked={dyslexiaFont}
                labelledBy="setting-dyslexia-font"
                srLabel={$_('settings.accessibility.dyslexia_font')}
                onchange={(v) => {
                dyslexiaFont = v;
                accessibilityPreview.dyslexiaFont = v;
            }}
            />
        </SettingsRow>
    {/if}

    <SettingsRow
        labelId="setting-reduced-motion"
        label={$_('settings.accessibility.reduced_motion')}
        description={$_('settings.accessibility.reduced_motion_desc')}
    >
        <SettingsToggle
            checked={reducedMotion}
            labelledBy="setting-reduced-motion"
            srLabel={$_('settings.accessibility.reduced_motion')}
            onchange={(v) => {
                reducedMotion = v;
                accessibilityPreview.reducedMotion = v;
            }}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-live-announcements"
        label={$_('settings.accessibility.live_announcements')}
        description={$_('settings.accessibility.live_announcements_desc')}
    >
        <SettingsToggle
            checked={liveAnnouncements}
            labelledBy="setting-live-announcements"
            srLabel={$_('settings.accessibility.live_announcements')}
            onchange={(v) => (liveAnnouncements = v)}
        />
    </SettingsRow>
</SettingsCard>
