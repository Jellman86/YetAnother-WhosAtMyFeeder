import { describe, expect, it } from 'vitest';

import settingsTabsSource from './SettingsTabs.svelte?raw';

describe('Settings navigation grouping', () => {
    it('groups every Settings route by the feeder workflow on desktop and mobile', () => {
        expect(settingsTabsSource).toContain('id: "pipeline"');
        expect(settingsTabsSource).toContain('id: "intelligence"');
        expect(settingsTabsSource).toContain('id: "operations"');
        expect(settingsTabsSource).toContain('id: "interface"');
        expect(settingsTabsSource).toContain('<optgroup label={group.label}>');
    });

    it('uses a stable accessible current-page state', () => {
        expect(settingsTabsSource).toContain("aria-current={activeTab === tab.id ? 'page' : undefined}");
        expect(settingsTabsSource).toContain('href={settingsHref(tab.id)}');
        expect(settingsTabsSource).toContain('toAppPath(`/settings/${tab}`)');
        expect(settingsTabsSource).toContain('event.metaKey');
        expect(settingsTabsSource).toContain('event.ctrlKey');
        expect(settingsTabsSource).toContain('focus-visible:ring-2');
        expect(settingsTabsSource).toContain('min-h-11');
        expect(settingsTabsSource).toContain('iconPath: string');
        expect(settingsTabsSource).not.toContain('icon: "');
        expect(settingsTabsSource).not.toContain('animate-pulse');
    });

    it('uses one quiet navigation surface instead of a grid of nested cards', () => {
        expect(settingsTabsSource).toContain('data-settings-navigation');
        expect(settingsTabsSource).toContain("group.id === 'operations'");
        expect(settingsTabsSource).toContain('xl:border-t-0');
        expect(settingsTabsSource).toContain('data-active-indicator');
        expect(settingsTabsSource).not.toContain('card-base');
        expect(settingsTabsSource).not.toContain('<section class="min-w-0 rounded-xl border');
        expect(settingsTabsSource).not.toContain('shadow-sm');
    });
});
