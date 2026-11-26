import { describe, expect, it } from 'vitest';
import openerSource from './RecordDialogs.svelte?raw';
import modalSource from './DetectionModal.svelte?raw';
import playerSource from './VideoPlayer.svelte?raw';
import aiSource from './record/RecordAiAnalysis.svelte?raw';

// Every Svelte file in the app, so a new place that opens a record cannot slip past.
const sources = import.meta.glob('../**/*.svelte', { eager: true, query: '?raw', import: 'default' }) as Record<string, string>;
const RECORD_PAGES = ['../pages/About.svelte', '../pages/Dashboard.svelte', '../pages/Events.svelte'];

describe('one record, the same controls wherever it opens', () => {
    it('opens the record and its video only through the shared opener', () => {
        for (const [path, source] of Object.entries(sources)) {
            if (path.endsWith('/RecordDialogs.svelte') || path === './RecordDialogs.svelte') continue;
            expect(source, path).not.toContain('<DetectionModal');
            expect(source, path).not.toContain('loadDetectionModal');
            expect(source, path).not.toContain('loadVideoPlayer');
        }
        for (const page of RECORD_PAGES) {
            expect(sources[page], page).toContain("import RecordDialogs from '../components/RecordDialogs.svelte';");
            expect(sources[page], page).toContain('<RecordDialogs');
            expect(sources[page], page).toContain('bind:record={selectedEvent}');
            expect(sources[page], page).toMatch(/bind:video\b/);
        }
    });

    it('lets no page take the video or the full visit away from a record', () => {
        for (const [path, source] of Object.entries(sources)) {
            expect(source, path).not.toContain('showVideoButton');
            expect(source, path).not.toMatch(/\breadOnly=/);
        }
        expect(modalSource).not.toContain('showVideoButton');
        expect(modalSource).not.toContain('readOnly');
        expect(aiSource).not.toContain('readOnly');
        // The opener always hands the record its play handler and the full-visit wiring.
        expect(openerSource).toContain('onPlayVideo={play}');
        expect(openerSource).toContain('onFetchFullVisit={fullVisitHandler}');
        expect(openerSource).toContain("fullVisitAvailable={fullVisitStore.availability[record.frigate_event] === 'available'}");
        expect(openerSource).toContain('onReclassify={reclassify}');
        expect(openerSource).toContain('<VideoPlayer');
        expect(openerSource).toContain('<LazyModal loader={loadDetectionModal}');
        expect(openerSource).toContain('<LazyModal loader={loadVideoPlayer}');
    });

    it('decides the video controls by access alone', () => {
        expect(modalSource).toContain("import { canWatchRecordVideo } from '../utils/record-access';");
        expect(modalSource).toContain('let canPlayVideo = $derived(!!onPlayVideo && canWatchRecordVideo(authStore)');
        expect(playerSource).toContain('canDownloadRecordClip(authStore, { shared: !!shareToken })');
        expect(openerSource).toContain('recordingClipsOn(settingsStore.settings, publicSettingsStore.settings) && canWatchRecordVideo(authStore)');
    });

    it('keeps page-specific work as named callbacks, never as missing controls', () => {
        const about = sources['../pages/About.svelte'];
        expect(about).toContain('onDeleteSuccess={(frigateEvent: string) => forgetVisit(frigateEvent)}');
        const events = sources['../pages/Events.svelte'];
        expect(events).toContain('onHideSuccess={');
        expect(events).toContain('onDeleteSuccess={');
        const dashboard = sources['../pages/Dashboard.svelte'];
        expect(dashboard).toContain('onbirdschanged={handleBirdsChanged}');
    });

    it('reads llmReady from the store and never copies state with an effect', () => {
        expect(openerSource).toContain('llmReady={settingsStore.llmReady}');
        expect(sources['../pages/Events.svelte']).not.toContain('llmReady = settingsStore.llmReady');
    });
});
