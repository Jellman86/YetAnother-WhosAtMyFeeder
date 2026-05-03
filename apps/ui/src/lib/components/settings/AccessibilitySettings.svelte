<script lang="ts">
    import { _, locale } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';

    let {
        highContrast = $bindable(false),
        dyslexiaFont = $bindable(false),
        liveAnnouncements = $bindable(true),
        reducedMotion = $bindable(false),
        zenMode = $bindable(false)
    }: {
        highContrast: boolean;
        dyslexiaFont: boolean;
        liveAnnouncements: boolean;
        reducedMotion: boolean;
        zenMode: boolean;
    } = $props();

    // OpenDyslexic font only supports Latin characters
    const latinLanguages = ['en', 'es', 'fr', 'de'];
    const currentLocale = $derived(typeof $locale === 'string' ? $locale : 'en');
    const showDyslexicFont = $derived(latinLanguages.includes(currentLocale));

    $effect(() => {
        document.documentElement.classList.toggle('high-contrast', highContrast);
    });
    $effect(() => {
        document.documentElement.classList.toggle('font-dyslexic', dyslexiaFont);
    });
    $effect(() => {
        document.documentElement.classList.toggle('reduced-motion', reducedMotion);
    });
    $effect(() => {
        document.documentElement.classList.toggle('zen-mode', zenMode);
    });
</script>

<SettingsCard icon="♿" title={$_('settings.accessibility.title')}>
    <SettingsRow
        labelId="setting-high-contrast"
        label={$_('settings.accessibility.high_contrast')}
        description={$_('settings.accessibility.high_contrast_desc')}
    >
        <SettingsToggle
            checked={highContrast}
            labelledBy="setting-high-contrast"
            srLabel={$_('settings.accessibility.high_contrast')}
            onchange={(v) => (highContrast = v)}
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
                onchange={(v) => (dyslexiaFont = v)}
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
            onchange={(v) => (reducedMotion = v)}
        />
    </SettingsRow>

    <SettingsRow
        labelId="setting-zen-mode"
        label={$_('settings.accessibility.zen_mode')}
        description={$_('settings.accessibility.zen_mode_desc')}
    >
        <SettingsToggle
            checked={zenMode}
            labelledBy="setting-zen-mode"
            srLabel={$_('settings.accessibility.zen_mode')}
            onchange={(v) => (zenMode = v)}
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
