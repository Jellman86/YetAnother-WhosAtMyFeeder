import { describe, expect, it } from 'vitest';
import appSource from '../../../App.svelte?raw';
import sidebarSource from '../Sidebar.svelte?raw';
import settingsSource from '../../pages/Settings.svelte?raw';
import eventsSource from '../../pages/Events.svelte?raw';
import tabsSource from './SettingsTabs.svelte?raw';
import connectionSource from './ConnectionSettings.svelte?raw';
import gardenBetaSource from './GardenBetaSettings.svelte?raw';
import gardenModelsSource from './GardenModelSetup.svelte?raw';
import gardenStatusSource from './GardenCollectionStatus.svelte?raw';
import betaCardSource from './BetaFeatureCard.svelte?raw';
import betaSectionSource from './BetaSection.svelte?raw';
import gardenServiceSource from './garden-service-status.svelte.ts?raw';
import detectionSource from './DetectionSettings.svelte?raw';
import notificationSource from './NotificationSettings.svelte?raw';
import enSettings from '../../i18n/locales/en/settings.json';

const en = { settings: enSettings };

describe('Garden animals is a beta feature', () => {
    it('has its own Beta features tab with a labelled switch that saves', () => {
        expect(tabsSource).toContain('id: "beta"');
        expect(settingsSource).toContain("{#if activeTab === 'beta'}");
        expect(settingsSource).toContain('<GardenBetaSettings');
        expect(betaCardSource).toContain('<SettingsToggle checked={enabled} labelledBy={nameId} srLabel={name} onchange={ontoggle} />');
        expect(gardenBetaSource).toContain('ontoggle={(next) => (enabled = next)}');
        expect(settingsSource).toContain('beta_garden_animals: betaGardenAnimals,');
        expect(settingsSource).toContain("store: s.beta_garden_animals ?? false");
    });

    it('lists beta features as cards under one plain-language intro', () => {
        const beta = settingsSource.slice(settingsSource.indexOf("{#if activeTab === 'beta'}"), settingsSource.indexOf("{#if activeTab === 'debug'}"));
        expect(beta).toContain('data-beta-intro');
        expect(beta).toContain('data-beta-feature-list');
        expect(beta).toMatch(/<li>\s*<LazyRoute loader=\{loadGardenBetaSettings\}[^\n]*\s*\{#snippet content\(GardenBetaSettings\)\}\s*<GardenBetaSettings/);
        expect(gardenBetaSource).toContain('<BetaFeatureCard');
        expect(en.settings.beta.intro).toMatch(/off until you turn it on/);
        expect(en.settings.beta.intro).toMatch(/keeps what it has already recorded/);
    });

    it('shows a feature\'s settings only while it is on, and what off means while it is off', () => {
        expect(betaCardSource).toMatch(/\{#if enabled\}\s*\{@render children\(\)\}\s*\{:else\}\s*\{@render off\(\)\}/);
        expect(betaCardSource).toContain('data-beta-status');
        expect(betaCardSource).toContain('{#if attention}<span class="attention-dot" aria-hidden="true"></span>{/if}');
    });

    it('groups Garden settings into the six collapsible sections, cameras and checks open by default', () => {
        const order = ['data-garden-next-steps', ...['cameras', 'checks', 'models', 'domestic', 'alerts', 'outcomes'].map(section => `id="garden-section-${section}"`)]
            .map(marker => gardenBetaSource.indexOf(marker));
        expect(order.every(index => index >= 0)).toBe(true);
        expect([...order].sort((a, b) => a - b)).toEqual(order);
        expect(gardenBetaSource).toContain('let sections = $state({ cameras: true, checks: true, models: false, domestic: false, alerts: false, outcomes: false });');
        // A heading that is the disclosure button, hidden rather than unmounted when closed.
        expect(betaSectionSource).toMatch(/<h5>\s*<button/);
        expect(betaSectionSource).toContain('aria-expanded={open}');
        expect(betaSectionSource).toContain('hidden={!open}');
        expect(betaSectionSource).toContain('min-h-11');
        expect(betaSectionSource).toContain('focus-visible:ring-2');
        expect(betaSectionSource).toContain("rotate-180");
    });

    it('reads Garden status once for the status line, models and collection status', () => {
        expect(gardenBetaSource).toContain('const service = new GardenServiceStatus();');
        expect(gardenBetaSource).toContain('if (!savedEnabled || !enabled) return;');
        expect(gardenModelsSource).not.toMatch(/fetchGarden(Identification|Motion)/);
        expect(gardenStatusSource).not.toMatch(/fetchGarden/);
        expect(gardenServiceSource).toContain('fetchGardenIdentification(signal), fetchGardenMotion(signal)');
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
        expect(gardenBetaSource).toContain('off={offNote}');
        expect(gardenBetaSource).toContain('data-garden-beta-settings');
        expect(gardenBetaSource).toContain('data-garden-beta-off-note');
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

    it('sets up Garden alerts once, in Notifications, and only summarises them here', () => {
        // Alerts choose channels, so they sit with the channels; Beta features links there.
        expect(gardenBetaSource).not.toContain('<GardenNotificationSettings');
        expect(gardenBetaSource).toContain('onclick={onOpenNotifications}');
        expect(settingsSource).toContain("onOpenNotifications={() => handleTabChange('notifications')}");
        expect(notificationSource).toMatch(/\{#if gardenBeta\}\s*<GardenNotificationSettings/);
        expect(notificationSource).toContain('birdChannels={policyChannels}');
        expect(settingsSource).toContain('gardenBeta={betaGardenAnimals}');
    });

    it('shows its thresholds as percentages through the settings primitives', () => {
        expect(gardenBetaSource).toContain('value={thresholdPercentText(motionConfidence)}');
        expect(gardenBetaSource).toContain('oninput={(value) => (motionConfidence = percentToThreshold(value))}');
        expect(gardenBetaSource).toContain('value={thresholdPercentText(namingThreshold)}');
        expect(gardenBetaSource).toContain('oninput={(value) => (namingThreshold = percentToThreshold(value))}');
        expect(gardenBetaSource).not.toMatch(/<input\b/);
    });

    it('sets up Garden models here, from saved state only, without touching bird models or settings', () => {
        expect(gardenBetaSource).toContain('<GardenModelSetup motionCameras={collectingMotion} {service} />');
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

    it('says honestly what turning it off does, in words that match the backend', () => {
        // garden_collection_cameras() returns none while the beta is off; Garden routes answer 404,
        // so the Explorer hides Garden; alerts and kept-bird routing both check the switch.
        expect(en.settings.beta.garden_off_note).toBe('Garden stops collecting new captures. Existing captures and settings are kept and come back when you turn it on again.');
        expect(en.settings.beta.garden_off_effects).toMatch(/hidden in the Explorer, its alerts stop, and birds you keep are recorded as wild birds/);
        for (const value of Object.values(en.settings.beta)) expect(value).not.toContain('—');
    });
});
