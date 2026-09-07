import { describe, expect, it } from 'vitest';
import bandSource from './DetectionStatusBand.svelte?raw';
import classifierApiSource from '../../api/classifier.ts?raw';

describe('the status band states the in-process fallback in words', () => {
    // When the isolated workers keep dying, classification silently moving
    // in-process would hide exactly the state a person must act on. Amber is
    // reserved for work that needs a person; this is that work.

    it('the API type carries the fallback state', () => {
        expect(classifierApiSource).toContain('worker_in_process_fallback?:');
    });

    it('the workers cell turns amber and says what is happening', () => {
        expect(bandSource).toContain('worker_in_process_fallback?.active');
        expect(bandSource).toContain('workerFallbackActive');
        expect(bandSource).toContain("settings.detection.band_worker_fallback'");
        expect(bandSource).toContain("settings.detection.band_worker_fallback_detail'");
        const fallbackBlock = bandSource.slice(bandSource.indexOf('workerFallbackActive}'));
        expect(fallbackBlock).toContain('text-amber-700');
    });
});

describe('the status band does not claim a runtime that has not loaded yet', () => {
    // Workers load on the first visit. Before that, the runtime cell shows the
    // plan, and "verified" would be a claim about something that has not
    // happened; the band says the model loads on first detection instead.

    it('the API type carries where the runtime figure comes from', () => {
        expect(classifierApiSource).toContain('runtime_source?:');
        expect(classifierApiSource).toContain("'planned'");
    });

    it('a planned runtime is labelled as such, ahead of the verified mark', () => {
        expect(bandSource).toContain("runtime_source === 'planned'");
        const runtimeCell = bandSource.slice(bandSource.indexOf("band_runtime')"));
        const plannedAt = runtimeCell.indexOf('runtimePlanned}');
        const verifiedAt = runtimeCell.indexOf('providerVerified}');
        expect(plannedAt).toBeGreaterThan(-1);
        expect(plannedAt).toBeLessThan(verifiedAt);
        expect(bandSource).toContain("settings.detection.band_runtime_planned'");
    });
});
