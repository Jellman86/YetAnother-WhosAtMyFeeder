import { describe, expect, it } from 'vitest';
import modal from './DetectionModal.svelte?raw';
import settings from './settings/DataSettings.svelte?raw';
import page from '../pages/Settings.svelte?raw';

describe('additional bird controls', () => {
    it('exposes an owner action on an explicit scan frame', () => {
        // The record owns the scan, bound to the explicit scan frame, and only for an owner.
        expect(modal).toContain('candidateId: scanFrameCandidate?.candidate_id ?? null');
        expect(modal).toMatch(/new BirdScan\(\s*\(\) => hasOwnerDetectionActions/);
        const component = modal.slice(modal.indexOf('<BirdScanControl'), modal.indexOf('<BirdScanControl') + 600);
        expect(component).toContain('scan={birdScan}');
        // It stands in the owner-only block that holds the identification actions, not on the photograph.
        const control = modal.indexOf('<BirdScanControl');
        const ownerBlock = modal.slice(modal.lastIndexOf('{#if hasOwnerDetectionActions}', control), control);
        expect(ownerBlock).toContain('data-detection-identification-actions');
        expect(modal.slice(modal.indexOf('{#snippet visitStrip()}'), modal.indexOf('{#snippet decision()}'))).not.toContain('<BirdScanControl');
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
