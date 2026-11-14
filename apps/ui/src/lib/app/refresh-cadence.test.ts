import { describe, expect, it } from 'vitest';

import appSource from '../../App.svelte?raw';
import cameraStatusSource from '../components/CameraStatus.svelte?raw';
import providerWarningSource from '../components/ProviderWarning.svelte?raw';
import recentAudioSource from '../components/RecentAudio.svelte?raw';
import systemHealthPanelSource from '../components/settings/SystemHealthPanel.svelte?raw';
import settingsSource from '../pages/Settings.svelte?raw';
import serverJobsSource from '../stores/server_jobs.svelte.ts?raw';
import { REFRESH_CADENCE_MS, SHELL_READINGS, readAtMostEvery, requestsPerIdleMinute } from './refresh-cadence';

describe('background refresh cadence', () => {
    it('keeps an idle owner page to a dozen shell requests a minute', () => {
        expect(requestsPerIdleMinute(SHELL_READINGS)).toBeLessThanOrEqual(12);
    });

    it('keeps the idle Dashboard under thirty requests a minute', () => {
        const dashboardOnly = [
            { reading: 'recentAudio', requests: 1 },
            { reading: 'providerWarning', requests: 2 }
        ] as const;
        // The Dashboard's own once-a-minute summary refresh reads seven endpoints.
        const summaryReads = 7;
        expect(requestsPerIdleMinute([...SHELL_READINGS, ...dashboardOnly]) + summaryReads).toBeLessThanOrEqual(30);
    });

    it('follows active work closely and idle work slowly', () => {
        expect(REFRESH_CADENCE_MS.serverJobsActive).toBeLessThan(REFRESH_CADENCE_MS.serverJobsIdle);
        expect(REFRESH_CADENCE_MS.analysisQueueActive).toBeLessThan(REFRESH_CADENCE_MS.analysisQueueIdle);
        expect(REFRESH_CADENCE_MS.providerWarningChecking).toBeLessThan(REFRESH_CADENCE_MS.providerWarning);
    });

    it.each([
        ['the shell', appSource, ['REFRESH_CADENCE_MS.ownerSystemChecks', 'REFRESH_CADENCE_MS.analysisQueueIdle', 'REFRESH_CADENCE_MS.mediaStorageCheck']],
        ['the camera status control', cameraStatusSource, ['REFRESH_CADENCE_MS.cameraHealth']],
        ['the accelerator warning', providerWarningSource, ['REFRESH_CADENCE_MS.providerWarning']],
        ['the Heard card', recentAudioSource, ['REFRESH_CADENCE_MS.recentAudio']],
        ['the system load chart', systemHealthPanelSource, ['REFRESH_CADENCE_MS.systemLoadHistory']],
        ['the Detection runtime line', settingsSource, ['REFRESH_CADENCE_MS.classifierRuntime']],
        ['the jobs store', serverJobsSource, ['REFRESH_CADENCE_MS.serverJobsIdle', 'REFRESH_CADENCE_MS.serverJobsActive']]
    ])('%s takes its rate from the shared cadence', (_name, source, constants) => {
        for (const constant of constants) expect(source).toContain(constant);
    });

    it.each([
        ['the accelerator warning', providerWarningSource],
        ['the jobs store', serverJobsSource]
    ])('%s does not read while the tab is hidden', (_name, source) => {
        expect(source).toContain('document.hidden');
        expect(source).toContain('visibilitychange');
    });
});

describe('readAtMostEvery', () => {
    it('reads once per interval and answers skipped calls with the last value', async () => {
        let clock = 0;
        let reads = 0;
        const read = readAtMostEvery(async () => ++reads, 1000, () => clock);

        expect(await read()).toBe(1);
        clock = 999;
        expect(await read()).toBe(1);
        clock = 1000;
        expect(await read()).toBe(2);
        expect(reads).toBe(2);
    });

    it('shares one request between overlapping callers', async () => {
        let reads = 0;
        const read = readAtMostEvery(async () => ++reads, 1000, () => 0);
        expect(await Promise.all([read(), read()])).toEqual([1, 1]);
    });

    it('reads again after a failure instead of remembering it', async () => {
        let reads = 0;
        const read = readAtMostEvery(async () => {
            reads += 1;
            if (reads === 1) throw new Error('unreachable');
            return reads;
        }, 1000, () => 0);

        await expect(read()).rejects.toThrow('unreachable');
        expect(await read()).toBe(2);
    });
});
