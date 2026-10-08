import { describe, expect, it } from 'vitest';
import modal from './DetectionModal.svelte?raw';
import settings from './settings/DataSettings.svelte?raw';
import page from '../pages/Settings.svelte?raw';

describe('additional bird controls', () => {
    it('exposes an owner action on an explicit scan frame', () => {
        const component = modal.slice(modal.indexOf('<BirdScanControl'), modal.indexOf('<BirdScanControl') + 600);
        expect(component).toContain('candidateId={scanFrameCandidate?.candidate_id ?? null}');
        expect(modal.slice(modal.indexOf('<BirdScanControl') - 100, modal.indexOf('<BirdScanControl'))).toContain('{#if hasOwnerDetectionActions}');
        const completion = modal.slice(modal.indexOf('async function refreshBirdsAfterScan'), modal.indexOf('async function handleGenerateSnapshotCandidates'));
        expect(completion).toContain('countedBirds = response.birds');
        expect(completion).not.toContain('handleApplySnapshot');
        expect(completion).not.toContain('snapshotRefreshToken =');
        expect(completion).not.toContain('currentSnapshotCandidateId =');
    });
    it('defaults automatic scans off without disabling manual effort controls', () => {
        expect(settings).toContain('cacheAutomaticMultiBirdScan = $bindable(false)');
        expect(settings).toContain('Automatically find additional birds');
        expect(settings).toMatch(/labelId="setting-automatic-multi-bird-scan"\s+layout="stacked"/);
        expect(settings).toContain('Applies to manual and automatic scans');
        expect(page).toContain('media_cache_automatic_multi_bird_scan: cacheAutomaticMultiBirdScan');
        expect(page).toContain('settings.media_cache_automatic_multi_bird_scan ?? false');
        const selector = settings.indexOf('labelId="setting-bird-scan-mode"');
        expect(selector).toBeLessThan(settings.indexOf('{#if cacheHighQualityEventSnapshots}', selector));
    });
});
