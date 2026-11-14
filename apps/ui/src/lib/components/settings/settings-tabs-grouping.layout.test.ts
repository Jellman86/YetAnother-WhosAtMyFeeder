import { describe, expect, it } from 'vitest';

import settingsTabsSource from './SettingsTabs.svelte?raw';
import settingsPageSource from './_primitives/SettingsPage.svelte?raw';

describe('Settings navigation', () => {
    it('groups every Settings route by the feeder workflow on desktop and mobile', () => {
        expect(settingsTabsSource).toContain('id: "pipeline"');
        expect(settingsTabsSource).toContain('id: "intelligence"');
        expect(settingsTabsSource).toContain('id: "operations"');
        expect(settingsTabsSource).toContain('id: "interface"');
        expect(settingsTabsSource).toContain('<optgroup label={group.label}>');
        // Species information sources are summarised in Integrations, not a tab of their own.
        expect(settingsTabsSource).not.toContain('id: "enrichment"');
    });

    it('uses real links with a stable current-page state that is not shown by colour alone', () => {
        expect(settingsTabsSource).toContain("aria-current={current ? 'page' : undefined}");
        expect(settingsTabsSource).toContain('href={settingsHref(tab.id)}');
        expect(settingsTabsSource).toContain('toAppPath(`/settings/${tab}`)');
        expect(settingsTabsSource).toContain('event.metaKey');
        expect(settingsTabsSource).toContain('focus-visible:ring-2');
        // The current section also carries a bar and heavier type, not only a tint.
        expect(settingsTabsSource).toContain('border-brand-600 bg-brand-50 font-semibold');
    });

    it('is a compact rail beside the settings on wide screens, with a skip link to them', () => {
        expect(settingsTabsSource).toContain('data-settings-navigation class="hidden lg:block"');
        expect(settingsTabsSource).toContain('data-settings-skip-link');
        expect(settingsPageSource).toContain('lg:flex lg:items-start');
        expect(settingsPageSource).toContain('id={contentId}');
        expect(settingsTabsSource).not.toContain('grid-cols-4');
        expect(settingsTabsSource).not.toContain('card-base');
    });

    it('offers the setup wizard as an ordinary button, never styled as a tab', () => {
        const wizardButtons = settingsTabsSource.match(/data-setup-wizard-action class="btn btn-secondary min-h-11/g) ?? [];
        expect(wizardButtons).toHaveLength(2);
    });
});
