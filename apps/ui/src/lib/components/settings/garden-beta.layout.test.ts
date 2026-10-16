import { describe, expect, it } from 'vitest';
import appSource from '../../../App.svelte?raw';
import sidebarSource from '../Sidebar.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';
import tabsSource from './SettingsTabs.svelte?raw';
import connectionSource from './ConnectionSettings.svelte?raw';
import en from '../../i18n/locales/en.json';

describe('Garden animals is a beta feature', () => {
    it('has its own Beta features tab with a labelled switch that saves', () => {
        expect(tabsSource).toContain('id: "beta"');
        expect(settingsSource).toContain("{#if activeTab === 'beta'}");
        expect(settingsSource).toContain('labelId="setting-beta-garden-animals"');
        expect(settingsSource).toContain('beta_garden_animals: betaGardenAnimals,');
        expect(settingsSource).toContain("store: s.beta_garden_animals ?? false");
    });

    it('hides the Garden navigation item until the beta is on', () => {
        expect(sidebarSource).toContain("settingsStore.settings?.beta_garden_animals === true");
        expect(sidebarSource).toContain("item.path !== '/garden' || gardenEnabled");
    });

    it('explains a switched-off Garden instead of loading a page that cannot load', () => {
        expect(appSource).toContain('data-garden-beta-off');
        expect(appSource).toContain("navigate('/settings/beta')");
    });

    it('hides the Garden camera options until the beta is on', () => {
        expect(connectionSource).toContain('{#if betaGardenAnimals}');
        expect(connectionSource).toContain('{#if betaGardenAnimals && gardenCameras.length > 0}');
    });

    it('says what turning it off does to saved captures', () => {
        expect(en.settings.beta.garden_animals_desc).toMatch(/saved captures are kept/);
        expect(en.settings.beta.subtitle).not.toContain('—');
    });
});
