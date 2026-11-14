import { describe, expect, it } from 'vitest';
import { scrollBehaviourFor } from './scroll-behaviour';
import detectionBandSource from '../components/settings/DetectionStatusBand.svelte?raw';
import notificationSentenceSource from '../components/settings/NotificationPolicySentence.svelte?raw';

describe('how Settings scrolls to a section', () => {
    it('glides only while neither the system nor the app asks for reduced motion', () => {
        expect(scrollBehaviourFor({ systemReducesMotion: false, appReducesMotion: false })).toBe('smooth');
        expect(scrollBehaviourFor({ systemReducesMotion: true, appReducesMotion: false })).toBe('auto');
        expect(scrollBehaviourFor({ systemReducesMotion: false, appReducesMotion: true })).toBe('auto');
    });

    it('is the behaviour every Settings jump uses, never a fixed smooth scroll', () => {
        for (const source of [detectionBandSource, notificationSentenceSource]) {
            expect(source).not.toContain("behavior: 'smooth'");
            expect(source).toContain('behavior: settingsScrollBehaviour()');
        }
    });
});
