import { describe, expect, it } from 'vitest';

import appSource from '../App.svelte?raw';
import audioHistorySource from './pages/AudioHistory.svelte?raw';
import cameraStatusSource from './components/CameraStatus.svelte?raw';
import captureWallSource from './components/CaptureWall.svelte?raw';
import dashboardSource from './pages/Dashboard.svelte?raw';
import deskContextCardsSource from './components/DeskContextCards.svelte?raw';
import footerSource from './components/Footer.svelte?raw';
import aboutSource from './pages/About.svelte?raw';
import instancePipelineSource from './components/InstancePipeline.svelte?raw';
import instanceSummarySource from './components/InstanceSummary.svelte?raw';
import providerWarningSource from './components/ProviderWarning.svelte?raw';
import jobCircuitBannerSource from './components/JobCircuitBanner.svelte?raw';
import errorsSource from './pages/Errors.svelte?raw';
import eventsSource from './pages/Events.svelte?raw';
import lazyRouteSource from './components/LazyRoute.svelte?raw';
import recentAudioSource from './components/RecentAudio.svelte?raw';
import settingsSource from './pages/Settings.svelte?raw';
import partLoadersSource from './components/settings/sections/part-loaders.ts?raw';
import camerasSectionSource from './components/settings/sections/CamerasSection.svelte?raw';

const sectionSources = Object.values(import.meta.glob<string>('./components/settings/sections/*.svelte', { query: '?raw', import: 'default', eager: true }));
import speciesSource from './pages/Species.svelte?raw';
import systemHealthPanelSource from './components/settings/SystemHealthPanel.svelte?raw';
import modelManagerSource from './pages/models/ModelManager.svelte?raw';
import modelSettingsSource from './components/settings/ModelSettings.svelte?raw';
import identificationSectionSource from './components/settings/sections/IdentificationSection.svelte?raw';

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

describe('Settings loads one section\'s parts at a time', () => {
    it.each(SETTINGS_TABS)('%s is its own chunk, fetched when its section is opened', (part) => {
        expect(partLoadersSource).toContain(`lazyComponent(() => import('../${part}.svelte'))`);
        for (const source of [settingsSource, ...sectionSources]) {
            expect(source).not.toMatch(new RegExp(`^\\s*import ${part} from`, 'm'));
        }
    });

    it('lets a lazily loaded part keep its two-way bindings to the form', () => {
        expect(lazyRouteSource).toContain('content?: Snippet<[LoadedPage]>');
        expect(lazyRouteSource).toContain('{@render content(Page)}');
        expect(camerasSectionSource).toContain('{#snippet content(ConnectionSettings)}');
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

    it('opening Settings joins the read the shell has just made, unless a kept draft needs a fresh one', () => {
        expect(settingsSource).toContain('loadSettings(false, !unsavedDraft.pendingFor(currentAccessIdentity()))');
        expect(settingsSource).toContain('await settingsStore.read(SHARED_SETTINGS_READ_MS)');
    });
});

describe('the Leaderboard does its work when it is looked at', () => {
    it('asks for a tile-sized photograph for each small cell of the wall', () => {
        expect(captureWallSource).toContain("getReelImageUrl(tile.frigateEvent, large(tile) ? 'card' : 'tile')");
        expect(captureWallSource).toContain('loading="lazy"');
    });

    it('reads a ranking row\'s reference picture when the row comes near the viewport', () => {
        // One portrait snippet draws both arrangements' rows.
        expect(speciesSource.match(/use:whenNearViewport=\{\(\) => void loadSpeciesInfo\(item\.species\)\}/g) ?? []).toHaveLength(1);
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

    it('opens the Leaderboard on a short contact sheet with every photograph sized to its cell', () => {
        // Each tile is one photograph request; the full wall is one press of "Show more visits" away.
        expect(captureWallSource).toContain('const CLOSED_ROWS = 3;');
        expect(captureWallSource).toContain('const CLOSED_ROWS_NARROW = 4;');
        expect(captureWallSource).toContain('width={tilePixels(tile)}');
        expect(captureWallSource).toContain('height={tilePixels(tile)}');
    });

    it('draws the wall skeleton with as many rows as the wall', () => {
        expect(captureWallSource).toContain('Array.from({ length: columns * rowCount }');
    });

    it('holds the system chart and the status line on the Health page', () => {
        expect(systemHealthPanelSource).toMatch(/class="min-h-96 [^"]*md:min-h-80[^"]*" data-system-health-loading/);
        expect(errorsSource).toContain('min-h-8 text-xs text-ink sm:min-h-4');
        // The verdict holds its height while the first reading is on its way.
        expect(errorsSource).toContain('flex min-h-28 flex-wrap');
    });

    it('takes the Explorer\'s first-read placeholders away whole, so a day strip arriving above the results moves nothing', () => {
        expect(eventsSource).toMatch(/\{#key pane\.state === 'first-load'\}[\s\S]*data-events-timeline[\s\S]*data-explorer-results=\{pane\.state\}[\s\S]*\{\/key\}/);
        // One day on the page says nothing the count has not said, so the strip waits for a second day.
        expect(eventsSource).toContain("{#if pane.state === 'results' && timelineBuckets.length > 1}");
        expect(eventsSource).not.toContain('data-events-timeline-placeholder');
    });
});

describe('one load asks each question once', () => {
    it('shares the status readings the shell, the page and its cards all show', () => {
        expect(cameraStatusSource).toContain('readCameraStatuses(controller.signal)');
        expect(deskContextCardsSource).toContain('readCameraStatuses(controller.signal)');
        expect(instancePipelineSource).toContain('readCameraStatuses(controller.signal)');
        expect(footerSource).toContain('await readVersion()');
        expect(aboutSource).toContain('await readVersion()');
        expect(settingsSource).toContain('await readVersion()');
        expect(instanceSummarySource).toContain('await readUpdateStatus()');
        expect(instanceSummarySource).toContain('await readClassifierStatus()');
        expect(instancePipelineSource).toContain('await readClassifierStatus()');
        expect(providerWarningSource).toContain('systemStatusStore.snapshot?.model');
        expect(appSource).toContain('analysisQueueStatusStore.ingest(snapshot.analysis);');
        // The circuit banner takes the queue from the pushed status and asks nothing on mount.
        expect(jobCircuitBannerSource).not.toContain('void analysisQueueStatusStore.refresh();');
    });

    it('reads the Dashboard day once the owner\'s Garden switch is known, not before and again after', () => {
        expect(dashboardSource).toContain('await settleGardenSwitch(signal);');
        expect(dashboardSource).toContain('if (available === readGardenAvailable || awaitingSettings) return;');
    });

    it('reads Garden again on a live-stream reconnect only, not on the first connect', () => {
        expect(appSource).toContain('if (authStore.hasOwnerAccess && liveStreamConnectedBefore) gardenHistory.invalidate();');
    });
});

describe('the live stream replaces polling where it announces changes', () => {
    it('reads the Dashboard day and its Heard figures from announcements while the stream is connected', () => {
        expect(dashboardSource).not.toContain('setInterval(');
        expect(dashboardSource).toContain('live: () => detectionsStore.connected,');
        expect(dashboardSource).toContain('live: () => audioFollowsLiveStream,');
        expect(dashboardSource).toContain('dayAudioReading?.changed();');
        // A failed read is retried rather than taken as fresh, and an announced call reads the species
        // checks too, since "Needs your call" counts what was heard.
        expect(dashboardSource).toContain('return summaryLoader.load();');
        expect(dashboardSource).toContain('announced && canReview ? readSpeciesChecksOnce() : Promise.resolve(true)');
        // Every part of the day, read by the scheduler or by the view itself, reports its failure
        // to the scheduler, and the two scheduled readers share one species-check read.
        expect(dashboardSource.match(/settled: \(\) => reportDayRead\(\)/g) ?? []).toHaveLength(2);
        expect(dashboardSource).toContain('settled: () => { summaryLoading = false; reportDayRead(); }');
        expect(dashboardSource).toContain('return !dayReadFailed.summary && !dayReadFailed.checks && !dayReadFailed.queue;');
        expect(dashboardSource).toContain('const readSpeciesChecksOnce = createSingleFlightRunner(() => speciesChecksLoader.load());');
        expect(recentAudioSource).toContain('async function loadAudio(): Promise<boolean> { return audioLoader.load(); }');
        expect(dashboardSource).toContain('quietMs: REFRESH_CADENCE_MS.liveSafetyRead,');
    });
});

describe('Settings reads operational data only for the section that shows it', () => {
    it('takes each section\'s readings when it opens, not every reading in every section', () => {
        const mount = settingsSource.slice(settingsSource.indexOf('onMount(async () => {'), settingsSource.indexOf('type SectionReading'));
        for (const read of ['loadCameras()', 'loadClassifierStatus()', 'loadMaintenanceStats()', 'loadCacheStats()', 'loadTaxonomyStatus()', 'loadVersion()']) {
            expect(mount).not.toContain(read);
        }
        const map = settingsSource.slice(settingsSource.indexOf('const READINGS_BY_SECTION'), settingsSource.indexOf('const readingsTaken'));
        for (const section of ['display', 'alerts', 'identification']) {
            expect(map).not.toContain(`${section}:`);
        }
        expect(settingsSource).toContain('untrack(() => readForSection(section, controller.signal));');
    });

    it('reads the storage figures before asking about a retention change saved from another tab', () => {
        expect(settingsSource).toContain('if (retentionShrinking && maintenanceStats === null) await loadMaintenanceStats();');
    });
});

describe('a reading whose length is only known once it lands moves nothing beneath it', () => {
    it('shows the Health page beneath the verdict once the verdict has its first reading', () => {
        expect(errorsSource).toContain("<SystemHealthPanel statusRead={readState !== 'reading'}>");
        // The timeline, and the side column beside it, wait for the reading together.
        expect(errorsSource).toMatch(/\{#if readState !== 'reading'\}\n(?:\s*<!--[\s\S]*?-->\n)?\s*<div class="grid[^"]*">\n\s*<div[^>]*data-health-main>\n\s*<Panel\n[^>]*data-health-timeline/);
        expect(systemHealthPanelSource).toContain('{#if !statusRead}');
        expect(systemHealthPanelSource).toContain('{#if details && statusRead}');
    });

    it('shows the Models tab beneath the model list once the list has its first answer, and keeps it on a refresh', () => {
        expect(modelManagerSource).toContain('{#if loading && !firstLoadSettled}');
        expect(modelManagerSource).toContain('firstLoadSettled = true;');
        expect(modelSettingsSource).toContain('bind:firstLoadSettled={modelsListed}');
        expect(modelSettingsSource).toContain('{#if onopenmodelevaluation && modelsListed}');
        // Hardware, under More options, is drawn only once the model list has its first answer.
        expect(identificationSectionSource).toContain('{#if modelsListed}\n            <div class="space-y-8" data-settings-hardware>');
    });
});
