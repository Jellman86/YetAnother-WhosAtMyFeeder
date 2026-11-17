import { describe, expect, it } from 'vitest';

import settingsTabsSource from './SettingsTabs.svelte?raw';
import settingsPageSource from './_primitives/SettingsPage.svelte?raw';

describe('Settings navigation', () => {
    it('lists the six task sections, the same on desktop and mobile, with no groups to scan', () => {
        expect(settingsTabsSource).toContain('SETTINGS_SECTION_ORDER.map((id) => ({ id, label: $_(`settings.sections.${id}`) }))');
        expect(settingsTabsSource.match(/\{#each sections as section \(section\.id\)\}/g) ?? []).toHaveLength(2);
        expect(settingsTabsSource).not.toContain('<optgroup');
        expect(settingsTabsSource).not.toContain('settings.tabs.groups');
    });

    it('uses real links with a stable current-page state that is not shown by colour alone', () => {
        expect(settingsTabsSource).toContain("aria-current={current ? 'page' : undefined}");
        expect(settingsTabsSource).toContain('href={sectionHref(section.id)}');
        expect(settingsTabsSource).toContain('toAppPath(settingsSectionPath(section))');
        expect(settingsTabsSource).toContain('event.metaKey');
        // The kit's sidebar-nav carries the focus ring and the 44 px target.
        expect(settingsTabsSource).toContain('class="sidebar-nav ');
        // The current section is the sidebar's recessed key with heavier type, never a bar on one edge.
        expect(settingsTabsSource).toContain("current ? 'sidebar-nav-active' : 'sidebar-nav-inactive'");
    });

    it('is a compact rail beside the settings when there is room for it in rem, with a skip link to them', () => {
        // Measured on the page as a container in rem, so doubled text gets the stacked layout.
        expect(settingsPageSource).toContain('<div class="@container space-y-6">');
        // From 42rem (a 1024 px window) the list sits beside the settings; doubled text stacks again.
        expect(settingsTabsSource).toContain('data-settings-navigation class="hidden @2xl:block"');
        expect(settingsTabsSource).toContain('flex flex-wrap items-end gap-3 @2xl:hidden" data-settings-compact-navigation');
        expect(settingsTabsSource).toContain('data-settings-skip-link');
        expect(settingsPageSource).toContain('@container (min-width: 42rem)');
        expect(settingsPageSource).toContain('grid-template-columns: 12rem minmax(0, 48rem);');
        // And from 68rem the status and the section's parts take a third column.
        expect(settingsPageSource).toContain('@container (min-width: 68rem)');
        expect(settingsPageSource).toContain('grid-template-columns: 12rem minmax(0, 48rem) minmax(15rem, 22rem);');
        expect(settingsPageSource).toContain('id={contentId}');
        expect(settingsTabsSource).not.toContain('grid-cols-4');
        expect(settingsTabsSource).not.toContain('card-base');
        // Labels use the one sentence-case style, not spaced capitals.
        expect(settingsTabsSource).not.toContain('eyebrow');
        expect(settingsTabsSource).not.toMatch(/uppercase|tracking-/);
    });

    it('offers the setup wizard as an ordinary button, never styled as a tab', () => {
        const wizardButtons = settingsTabsSource.match(/data-setup-wizard-action class="btn btn-secondary min-h-11/g) ?? [];
        expect(wizardButtons).toHaveLength(2);
    });
});
