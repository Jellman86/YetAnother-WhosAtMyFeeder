import { describe, expect, it } from 'vitest';
import appSource from '../../../App.svelte?raw';
import sidebarSource from '../Sidebar.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';
import tabsSource from './SettingsTabs.svelte?raw';
import connectionSource from './ConnectionSettings.svelte?raw';
import gardenBetaSource from './GardenBetaSettings.svelte?raw';
import gardenModelsSource from './GardenModelSetup.svelte?raw';
import detectionSource from './DetectionSettings.svelte?raw';
import en from '../../i18n/locales/en.json';

describe('Garden animals is a beta feature', () => {
    it('has its own Beta features tab with a labelled switch that saves', () => {
        expect(tabsSource).toContain('id: "beta"');
        expect(settingsSource).toContain("{#if activeTab === 'beta'}");
        expect(settingsSource).toContain('<GardenBetaSettings');
        expect(gardenBetaSource).toContain('labelId="setting-beta-garden-animals"');
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

    it('keeps every Garden setting with its switch, hidden until the beta is on', () => {
        expect(gardenBetaSource).toContain('{#if !enabled}');
        expect(gardenBetaSource).toContain('{:else}');
        expect(gardenBetaSource).toContain('data-garden-beta-settings');
        expect(connectionSource).toContain('settings.cameras.garden_moved');
    });

    it('sets up Garden models here, from saved state only, without touching bird models or settings', () => {
        expect(gardenBetaSource).toContain('<GardenModelSetup {motionCameras} />');
        expect(gardenModelsSource).toContain("settingsStore.settings?.beta_garden_animals === true");
        expect(gardenModelsSource).toContain('installGardenModel(row.install.variant)');
        expect(gardenModelsSource).toContain('installGardenMotion()');
        expect(gardenModelsSource).not.toMatch(/updateSettings|activateModel|\/api\/models|uploadDiagnostic/);
        expect(gardenModelsSource).not.toContain('settingsStore.update');
    });

    it('leaves Garden controls out of Detection and links daily review instead of duplicating it', () => {
        expect(detectionSource).not.toMatch(/garden/i);
        expect(gardenBetaSource).not.toContain('fetchGarden(');
        expect(gardenBetaSource).toContain("onNavigate?.('/garden')");
    });

    it('says what turning it off does to saved captures', () => {
        expect(en.settings.beta.garden_animals_desc).toMatch(/saved captures are kept/);
        expect(en.settings.beta.subtitle).not.toContain('—');
    });
});
