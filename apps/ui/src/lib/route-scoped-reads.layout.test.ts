import { describe, expect, it } from 'vitest';
import appSource from '../App.svelte?raw';
import dashboardSource from './pages/Dashboard.svelte?raw';
import healthSource from './pages/Errors.svelte?raw';
import settingsSource from './pages/Settings.svelte?raw';

function body(source: string, signature: string): string {
    const start = source.indexOf(signature);
    expect(start).toBeGreaterThan(-1);
    const next = source.indexOf('\n    async function ', start + signature.length);
    return source.slice(start, next === -1 ? undefined : next);
}

describe('each read belongs to the route and task that shows it', () => {
    it('reads recent history on the Dashboard, not at startup on every route', () => {
        expect(appSource).not.toContain('detectionsStore.loadInitial();');
        expect(dashboardSource).toContain('const stopFollowingHistory = detectionsStore.follow();');
        expect(dashboardSource).toContain('stopFollowingHistory();');
        expect(healthSource).not.toContain('detectionsStore');
    });

    it('loads the Settings form without any section\'s helper data', () => {
        const loadSettings = body(settingsSource, 'async function loadSettings(');
        expect(loadSettings).not.toContain('fetchAudioSources');
        expect(loadSettings).not.toContain('loadRecordingClipCapability');
        // BirdNET-Go's sources are read only when its camera mapping is shown: under its advanced
        // options in Integrations, with audio on (settings-tab-readings.spec.ts counts the reads).
        expect(settingsSource).toContain("cameras: ['cameras', 'recordingClips'],");
        expect(settingsSource).toContain("activeSection === 'integrations' && disclosures.isOpen(BIRDNET_MAPPING_DISCLOSURE) === true && birdnetEnabled");
        expect(settingsSource).toContain("integrations: ['cameras'],");
        expect(settingsSource).toContain("readOnce('audioSources', sectionReadings.signal)");
        expect(settingsSource).toContain("access: ['version'],");
        expect(settingsSource).toContain("storage: ['classifier', 'storage', 'cache', 'backfill']");
    });

    it('follows a running backfill from the pushed jobs instead of asking from every section', () => {
        expect(settingsSource).not.toMatch(/Promise\.all\(\[\s*loadSettings\([^)]*\),\s*loadBackfillStatus\(\)/);
        expect(settingsSource).toContain("(job.kind === 'backfill' || job.kind === 'weather_backfill') && job.status === 'running'");
    });
});
