<script lang="ts">
    import { tick } from 'svelte';
    import { _, locale } from 'svelte-i18n';
    import SettingsCard from './_primitives/SettingsCard.svelte';
    import SettingsRow from './_primitives/SettingsRow.svelte';
    import SettingsToggle from './_primitives/SettingsToggle.svelte';
    import { accessibilityPreview } from '../../stores/accessibility_preview.svelte';
    import { accessibilityApplied } from '../../stores/accessibility_applied.svelte';
    import { accessibilityDevice, type AccessibilityChoice } from '../../settings/accessibility-device.svelte';
    import type { AccessibilityDraft } from '../../settings/accessibility-section';

    let {
        draft,
        onchange,
        region
    }: {
        /**
         * `main`: this device's own choices, which change at once and are never saved. `more`: the
         * defaults for everyone, which guests and new devices follow once they are saved.
         */
        region: 'main' | 'more';
        /** The saved-for-everyone Accessibility choices as currently edited; Apply saves them. */
        draft: AccessibilityDraft;
        onchange: (patch: Partial<AccessibilityDraft>) => void;
    } = $props();

    // OpenDyslexic has Latin letters only. Elsewhere its row is offered only while it is on, here or
    // for everyone, so a choice made in another language can always be set back.
    const latinLanguages = ['en', 'es', 'fr', 'de', 'it', 'pt'];
    const currentLocale = $derived(typeof $locale === 'string' ? $locale : 'en');
    const latinLocale = $derived(latinLanguages.includes(currentLocale));
    const showDyslexicFont = $derived(
        latinLocale || accessibilityApplied.dyslexiaFont || accessibilityApplied.defaultFor('dyslexiaFont') || draft.dyslexiaFont
    );
    const dyslexicFontDescription = $derived(
        latinLocale
            ? $_('settings.accessibility.dyslexia_font_desc')
            : `${$_('settings.accessibility.dyslexia_font_desc')} ${$_('settings.accessibility.dyslexia_font_latin_only', { default: 'It has Latin letters only, so text in this language stays as it is.' })}`
    );

    interface Choice {
        key: AccessibilityChoice;
        id: string;
        label: string;
        description: string;
    }

    const choices: Choice[] = $derived([
        {
            key: 'highContrast',
            id: 'high-contrast',
            label: $_('settings.accessibility.high_contrast'),
            description: $_('settings.accessibility.high_contrast_desc')
        },
        ...(showDyslexicFont
            ? [{
                key: 'dyslexiaFont' as const,
                id: 'dyslexia-font',
                label: $_('settings.accessibility.dyslexia_font'),
                description: dyslexicFontDescription
            }]
            : []),
        {
            key: 'reducedMotion',
            id: 'reduced-motion',
            label: $_('settings.accessibility.reduced_motion'),
            description: $_('settings.accessibility.reduced_motion_desc')
        },
        {
            key: 'liveAnnouncements',
            id: 'live-announcements',
            label: $_('settings.accessibility.live_announcements'),
            description: $_('settings.accessibility.live_announcements_desc')
        }
    ]);

    /** The unsaved default this device is showing for a choice it follows, or null. */
    function previewOf(key: AccessibilityChoice): boolean | null {
        return key === 'liveAnnouncements' ? null : accessibilityPreview[key];
    }

    /** What this device shows: its own choice, else the default being edited, else the saved default. */
    function appliedOf(key: AccessibilityChoice): boolean {
        return accessibilityApplied[key];
    }

    function onOff(value: boolean): string {
        return value
            ? $_('settings.accessibility.state_on', { default: 'on' })
            : $_('settings.accessibility.state_off', { default: 'off' });
    }

    let deviceCard = $state<HTMLElement | null>(null);

    // The button goes with the choice it clears, so focus moves to the row's switch, whose
    // description then says it follows the default: the result of the action, read out.
    async function useDefault(choice: Choice): Promise<void> {
        accessibilityDevice.set(choice.key, null);
        await tick();
        deviceCard?.querySelector<HTMLElement>(`button[aria-labelledby="setting-${choice.id}"]`)?.focus();
    }
</script>

{#if region === 'main'}
<div bind:this={deviceCard}>
<SettingsCard
        id="settings-group-accessibility-device"
    title={$_('settings.accessibility.device_title', { default: 'Accessibility on this device' })}
    description={$_('settings.accessibility.device_scope', { default: 'These change at once, in this browser only, and need no saving. Until you set one here, this device follows the default for everyone under More options.' })}
>
    {#each choices as choice (choice.key)}
        {@const own = accessibilityDevice.get(choice.key)}
        {@const saved = accessibilityApplied.defaultFor(choice.key)}
        {@const previewed = own === undefined ? previewOf(choice.key) : null}
        <SettingsRow labelId="setting-{choice.id}" label={choice.label} description={choice.description}>
            <div class="flex flex-col items-start gap-2 md:items-end">
                <SettingsToggle
                    checked={appliedOf(choice.key)}
                    labelledBy="setting-{choice.id}"
                    describedBy="setting-{choice.id}-source"
                    srLabel={choice.label}
                    onchange={(v) => accessibilityDevice.set(choice.key, v)}
                />
                <p id="setting-{choice.id}-source" class="text-sm text-muted md:text-right" data-accessibility-source={own !== undefined ? 'device' : previewed !== null ? 'preview' : 'default'}>
                    {#if own !== undefined}
                        {$_('settings.accessibility.own_choice', { default: 'Set on this device. The default for everyone is {state}.', values: { state: onOff(saved) } })}
                    {:else if previewed !== null}
                        {$_('settings.accessibility.previewing_default', { default: 'Previewing the unsaved default for everyone ({state})', values: { state: onOff(previewed) } })}
                    {:else}
                        {$_('settings.accessibility.follows_default', { default: 'Follows the default for everyone ({state})', values: { state: onOff(saved) } })}
                    {/if}
                </p>
                {#if own !== undefined}
                    <button
                        type="button"
                        class="btn btn-ghost min-h-11"
                        aria-label={`${$_('settings.accessibility.use_default', { default: 'Use the default' })}: ${choice.label}`}
                        onclick={() => useDefault(choice)}
                    >
                        {$_('settings.accessibility.use_default', { default: 'Use the default' })}
                    </button>
                {/if}
            </div>
        </SettingsRow>
    {/each}
</SettingsCard>
</div>
{:else}
<SettingsCard
        id="settings-group-accessibility-defaults"
    nested
    titleId="accessibility-defaults-title"
    title={$_('settings.accessibility.defaults_title', { default: 'Defaults for everyone' })}
    description={$_('settings.accessibility.defaults_scope', { default: 'Guests and devices with no choice of their own follow these, once you save. A device with its own choice keeps it. Until you save, this device previews the ones it follows.' })}
>
    <!-- One row per saved field, written out so each field's control can be traced to it. Each
         switch is named with the card's title, so a screen reader never hears two switches called
         the same as this device's ones. -->
    <SettingsRow labelId="setting-default-high-contrast" label={$_('settings.accessibility.high_contrast')} description={$_('settings.accessibility.high_contrast_desc')}>
        <SettingsToggle
            checked={draft.highContrast}
            labelledBy="accessibility-defaults-title setting-default-high-contrast"
            srLabel={$_('settings.accessibility.high_contrast')}
            onchange={(v) => onchange({ highContrast: v })}
        />
    </SettingsRow>

    {#if showDyslexicFont}
        <SettingsRow labelId="setting-default-dyslexia-font" label={$_('settings.accessibility.dyslexia_font')} description={dyslexicFontDescription}>
            <SettingsToggle
                checked={draft.dyslexiaFont}
                labelledBy="accessibility-defaults-title setting-default-dyslexia-font"
                srLabel={$_('settings.accessibility.dyslexia_font')}
                onchange={(v) => onchange({ dyslexiaFont: v })}
            />
        </SettingsRow>
    {/if}

    <SettingsRow labelId="setting-default-reduced-motion" label={$_('settings.accessibility.reduced_motion')} description={$_('settings.accessibility.reduced_motion_desc')}>
        <SettingsToggle
            checked={draft.reducedMotion}
            labelledBy="accessibility-defaults-title setting-default-reduced-motion"
            srLabel={$_('settings.accessibility.reduced_motion')}
            onchange={(v) => onchange({ reducedMotion: v })}
        />
    </SettingsRow>

    <SettingsRow labelId="setting-default-live-announcements" label={$_('settings.accessibility.live_announcements')} description={$_('settings.accessibility.live_announcements_desc')}>
        <SettingsToggle
            checked={draft.liveAnnouncements}
            labelledBy="accessibility-defaults-title setting-default-live-announcements"
            srLabel={$_('settings.accessibility.live_announcements')}
            onchange={(v) => onchange({ liveAnnouncements: v })}
        />
    </SettingsRow>
</SettingsCard>
{/if}
