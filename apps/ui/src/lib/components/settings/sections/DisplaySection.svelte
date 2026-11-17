<script lang="ts">
    import { _ } from 'svelte-i18n';
    import LazyRoute from '../../LazyRoute.svelte';
    import type { Theme } from '../../../stores/theme.svelte';
    import type { AppearanceDraft } from '../../../settings/appearance-section';
    import type { AccessibilityDraft } from '../../../settings/accessibility-section';
    import { loadAccessibilitySettings, loadAppearanceSettings } from './part-loaders';

    // Display: how YA-WAMF looks and reads. Holds what were the Appearance and Accessibility tabs.
    interface Props {
        currentTheme: Theme;
        currentLocale: string;
        appearanceDraft: AppearanceDraft;
        onAppearanceChange: (patch: Partial<AppearanceDraft>) => void;
        setTheme: (theme: Theme) => void;
        setLanguage: (language: string) => Promise<void>;
        accessibilityDraft: AccessibilityDraft;
        onAccessibilityChange: (patch: Partial<AccessibilityDraft>) => void;
    }

    let {
        currentTheme,
        currentLocale,
        appearanceDraft,
        onAppearanceChange,
        setTheme,
        setLanguage,
        accessibilityDraft,
        onAccessibilityChange
    }: Props = $props();
</script>

<div class="space-y-8" data-settings-section="display">
    <div class="space-y-8" data-settings-part="appearance">
        <LazyRoute
            loader={loadAppearanceSettings}
            label={$_('settings.tabs.appearance')}
            props={{
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
</div>
