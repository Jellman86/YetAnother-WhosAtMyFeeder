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
});
