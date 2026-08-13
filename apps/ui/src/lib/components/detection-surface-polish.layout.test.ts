import { describe, expect, it } from 'vitest';

import detectionCardSource from './DetectionCard.svelte?raw';
import detectionModalSource from './DetectionModal.svelte?raw';

describe('detection surface polish', () => {
    it('keeps event cards quiet and media-led', () => {
        expect(detectionCardSource).toContain('data-detection-card');
        expect(detectionCardSource).toContain('hover:border-brand-500/40');
        expect(detectionCardSource).not.toContain('hover:-translate-y-1.5');
        expect(detectionCardSource).not.toContain('group-hover:rotate-1');
        expect(detectionCardSource).not.toContain('ring-1 ring-slate-200/40');
        expect(detectionCardSource).toContain('inline-flex h-11 w-11 items-center justify-center');
        expect(detectionCardSource).toContain("let isManualObservation = $derived(detection.observation_source === 'manual_upload')");
        expect(detectionCardSource).not.toContain("manual_observation.uploaded");
    });

    it('preserves the full snapshot and exposes a labelled, responsive dialog', () => {
        expect(detectionModalSource).toContain('data-detection-detail-modal');
        expect(detectionModalSource).toContain('aria-labelledby="detection-modal-title"');
        expect(detectionModalSource).toContain('id="detection-modal-title"');
        expect(detectionModalSource).toContain('data-detection-media-ambient');
        expect(detectionModalSource).toContain('object-contain');
        expect(detectionModalSource).toContain('max-h-[100dvh]');
        expect(detectionModalSource).toContain('bg-gradient-to-br from-slate-900 via-slate-950 to-brand-950');
        expect(detectionModalSource).toContain('class="absolute top-4 right-4 z-40 inline-flex h-11 w-11');
    });

    it('keeps implementation identity collapsed until it is requested', () => {
        expect(detectionModalSource).toContain('data-detection-technical-identity');
        expect(detectionModalSource).toContain('<details');
        expect(detectionModalSource).toContain('group order-last border-t');
        expect(detectionModalSource).toContain('{detection.frigate_event}');
    });

    it('uses section dividers for supporting context instead of stacked feature cards', () => {
        expect(detectionModalSource).toContain('data-detection-audio-section');
        expect(detectionModalSource).toContain('data-detection-weather-section');
        expect(detectionModalSource).toMatch(/data-detection-audio-section[^>]+border-t/);
        expect(detectionModalSource).toMatch(/data-detection-weather-section[^>]+border-t/);
    });

    it('shows honest snapshot options and keeps integration rows to measured states', () => {
        expect(detectionModalSource).toContain('data-detection-frame-strip');
        // Candidates are owner-gated, so a guest gets no strip rather than an empty one.
        expect(detectionModalSource).toContain('authStore.hasOwnerAccess ? snapshotCandidates.filter');
        // "no matching call" from a disabled BirdNET would report a measurement never taken.
        expect(detectionModalSource).toContain('{#if birdnetEnabled && !isManualObservation}');
        expect(detectionModalSource).toContain('effectiveAudioConfirmed');
        expect(detectionModalSource).toContain('audioContextLoading');
        expect(detectionModalSource).toContain("detection.snapshot_options");
        expect(detectionModalSource).toContain('openSnapshotCandidate(candidate)');
        expect(detectionModalSource).toContain('data-detection-facts');
        expect(detectionModalSource).toContain('data-detection-identity');
    });

    it('names the actions by what they do', () => {
        expect(detectionModalSource).toContain('data-detection-confirm');
        expect(detectionModalSource).toContain("actions.confirm_species");
        expect(detectionModalSource).toContain("actions.pick_species");
        expect(detectionModalSource).toContain('applyManualTagResult(detection, result)');
        // Confirming an already-confirmed or unnamed detection is not offered.
        expect(detectionModalSource).toContain('{#if !detection.manual_tagged && !isUnknownSpecies}');
    });

    it('preserves the complete stored image unless a matching full frame is available', () => {
        expect(detectionModalSource).toContain('findMatchingFullFrameCandidate');
        expect(detectionModalSource).toContain("canShowFullFrame ? 'object-cover' : 'object-contain'");
    });

    it('discovers late BirdNET context independently of stored audio hints', () => {
        expect(detectionModalSource).toContain('fetchEventAudioContext');
        expect(detectionModalSource).toContain('controller.abort()');
        expect(detectionModalSource).toContain('for (const audio of audioContext)');
        expect(detectionModalSource).not.toContain('if (!hasAudioContext) return;');
        expect(detectionModalSource).toContain('if (detection.observation_source === \'manual_upload\')');
        expect(detectionModalSource).toContain('audioContext.filter((audio) => audio.matches_visual)');
        expect(detectionModalSource).toContain('!isManualObservation && (effectiveAudioConfirmed');
    });

    it('shows retained upload coordinates without BirdNET context', () => {
        expect(detectionModalSource).toContain('detection.observation_latitude');
        expect(detectionModalSource).toContain('data-manual-observation-location');
    });
});
