import { describe, expect, it } from 'vitest';

import appSource from '../App.svelte?raw';
import audioHistorySource from './pages/AudioHistory.svelte?raw';
import cameraStatusSource from './components/CameraStatus.svelte?raw';
import captureWallSource from './components/CaptureWall.svelte?raw';
import errorsSource from './pages/Errors.svelte?raw';
import eventsSource from './pages/Events.svelte?raw';
import lazyRouteSource from './components/LazyRoute.svelte?raw';
import recentAudioSource from './components/RecentAudio.svelte?raw';
import settingsSource from './pages/Settings.svelte?raw';
import speciesSource from './pages/Species.svelte?raw';
import systemHealthPanelSource from './components/settings/SystemHealthPanel.svelte?raw';

const SETTINGS_TABS = [
    'ConnectionSettings',
    'DetectionSettings',
    'NotificationSettings',
    'IntegrationSettings',
    'AuthenticationSettings',
    'DataSettings',
    'GardenBetaSettings',
    'AppearanceSettings',
    'AccessibilitySettings',
    'EnrichmentSettings',
    'AISettings'
];

describe('Settings loads one tab at a time', () => {
    it.each(SETTINGS_TABS)('%s is its own chunk, fetched when its tab is opened', (tab) => {
        expect(settingsSource).toContain(`lazyComponent(() => import('../components/settings/${tab}.svelte'))`);
        expect(settingsSource).not.toMatch(new RegExp(`^\\s*import ${tab} from`, 'm'));
    });

    it('lets a lazily loaded tab keep its two-way bindings to the form', () => {
        expect(lazyRouteSource).toContain('content?: Snippet<[LoadedPage]>');
        expect(lazyRouteSource).toContain('{@render content(Page)}');
        expect(settingsSource).toContain('{#snippet content(ConnectionSettings)}');
    });
});

describe('one settings request answers the whole page load', () => {
    it.each([
        ['the camera status control', cameraStatusSource],
        ['the Heard card', recentAudioSource],
        ['Audio history', audioHistorySource]
    ])('%s reads the settings the shell already holds', (_name, source) => {
        expect(source).toContain('await settingsStore.read()');
        expect(source).not.toContain('fetchSettings');
    });

    it('opening Settings joins the read the shell has just made', () => {
        expect(settingsSource).toContain('loadSettings(false, true)');
        expect(settingsSource).toContain('await settingsStore.read(SHARED_SETTINGS_READ_MS)');
    });
});

describe('the Leaderboard does its work when it is looked at', () => {
    it('asks for a tile-sized photograph for each small cell of the wall', () => {
        expect(captureWallSource).toContain("getReelImageUrl(tile.frigateEvent, large(tile) ? 'card' : 'tile')");
        expect(captureWallSource).toContain('loading="lazy"');
    });

    it('reads a ranking row\'s reference picture when the row comes near the viewport', () => {
        expect(speciesSource.match(/use:whenNearViewport=\{\(\) => void loadSpeciesInfo\(item\.species\)\}/g) ?? []).toHaveLength(2);
        expect(speciesSource).not.toContain('for (const row of showcaseRows) void loadSpeciesInfo(row.key);');
        expect(speciesSource).not.toContain('sortedSpecies().slice(0, 20)');
    });

    it('draws its charts when they come near the viewport', () => {
        expect(speciesSource).not.toContain('use:chartjs=');
        expect(speciesSource.match(/use:chartjsWhenNear=/g) ?? []).toHaveLength(3);
    });
});

describe('content that arrives late has its space held', () => {
    it('keeps the footer below the fold while a page reads its data', () => {
        expect(appSource).toMatch(/<main id="main-content" class="min-h-svh /);
    });

    it('draws the wall skeleton with as many rows as the wall', () => {
        expect(captureWallSource).toContain('Array.from({ length: columns * rowCount }');
    });

    it('holds the system chart, the status line and the header reading on the Health tab', () => {
        expect(systemHealthPanelSource).toMatch(/class="min-h-96 [^"]*md:min-h-80[^"]*" data-system-health-loading/);
        expect(errorsSource).toContain('min-h-8 text-xs text-slate-600 sm:min-h-4');
        expect(errorsSource).toContain("refreshedAgoText() ? '' : 'invisible'");
    });

    it('holds the Explorer day strip\'s space while the first page is read', () => {
        expect(eventsSource).toMatch(/\{:else if pane\.state === 'first-load'\}\s*<!--[^>]*-->\s*<div class="pb-4 pt-1" aria-hidden="true" data-events-timeline-placeholder>/);
    });
});
