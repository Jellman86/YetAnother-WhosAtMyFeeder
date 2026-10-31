import { describe, expect, it } from 'vitest';
import appSource from '../../../App.svelte?raw';
import sidebarSource from '../Sidebar.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';
import eventsSource from '../../pages/Events.svelte?raw';
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

    it('has no separate Garden page: old links open Garden review in the Explorer', () => {
        expect(sidebarSource).not.toContain("'/garden'");
        expect(appSource).not.toContain('pages/Garden.svelte');
        expect(appSource).toContain("const GARDEN_REVIEW_ROUTE = '/events?visitors=garden&review=pending';");
        expect(appSource).toContain("if (path === '/garden' || path.startsWith('/garden/'))");
    });

    it('explains a switched-off Garden in the Explorer instead of silently showing birds', () => {
        expect(eventsSource).toContain('data-garden-beta-off');
        expect(eventsSource).toContain("toAppPath('/settings/beta')");
    });

    it('keeps every Garden setting with its switch, hidden until the beta is on', () => {
        expect(gardenBetaSource).toContain('{#if !enabled}');
        expect(gardenBetaSource).toContain('{:else}');
        expect(gardenBetaSource).toContain('data-garden-beta-settings');
    });

    it('chooses Garden cameras once, in Connection, and only summarises them here', () => {
        // Two camera lists that marked "chosen" differently were the problem (SET-05); Beta
        // features keeps a summary with a way to the one list.
        expect(gardenBetaSource).not.toContain('type="radio"');
        expect(gardenBetaSource).not.toContain('availableCameras');
        expect(gardenBetaSource).toContain('data-garden-camera-summary');
        expect(gardenBetaSource).toContain('onclick={onOpenCameras}');
        expect(settingsSource).toContain('onOpenCameras={openCameraSettings}');
        expect(connectionSource).toContain('gardenEnabled: betaGardenAnimals');
    });

    it('follows its own setup steps: cameras and labels, then models, naming and alerts', () => {
        const order = ['data-garden-setup-steps', 'data-garden-collect', '<GardenModelSetup', 'data-garden-naming', '<GardenNotificationSettings', 'data-garden-outcomes']
            .map(marker => gardenBetaSource.indexOf(marker));
        expect(order.every(index => index >= 0)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
    });

    it('shows its thresholds as percentages through the settings primitives', () => {
        expect(gardenBetaSource).toContain('value={thresholdPercentText(motionConfidence)}');
        expect(gardenBetaSource).toContain('oninput={(value) => (motionConfidence = percentToThreshold(value))}');
        expect(gardenBetaSource).toContain('value={thresholdPercentText(namingThreshold)}');
        expect(gardenBetaSource).toContain('oninput={(value) => (namingThreshold = percentToThreshold(value))}');
        expect(gardenBetaSource).not.toMatch(/<input\b/);
    });

    it('sets up Garden models here, from saved state only, without touching bird models or settings', () => {
        expect(gardenBetaSource).toContain('<GardenModelSetup motionCameras={collectingMotion} />');
        expect(gardenModelsSource).toContain("settingsStore.settings?.beta_garden_animals === true");
        expect(gardenModelsSource).toContain('installGardenModel(row.install.variant)');
        expect(gardenModelsSource).toContain('installGardenMotion()');
        expect(gardenModelsSource).not.toMatch(/updateSettings|activateModel|\/api\/models|uploadDiagnostic/);
        expect(gardenModelsSource).not.toContain('settingsStore.update');
    });

    it('leaves Garden controls out of Detection and links daily review instead of duplicating it', () => {
        expect(detectionSource).not.toMatch(/garden/i);
        expect(gardenBetaSource).not.toContain('fetchGarden(');
        expect(gardenBetaSource).toContain("onNavigate?.('/events?visitors=garden&review=pending')");
    });

    it('says what turning it off does to saved captures', () => {
        expect(en.settings.beta.garden_animals_desc).toMatch(/saved captures are kept/);
        expect(en.settings.beta.subtitle).not.toContain('—');
    });
});
