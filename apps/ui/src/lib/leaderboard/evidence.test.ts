import { describe, expect, it } from 'vitest';
import { evidenceFor, isCorroborated } from './evidence';

const audioOn = { audioKnown: true };
const audioOff = { audioKnown: false };

describe('evidenceFor', () => {
    it('prefers a person naming the bird over anything the machines found', () => {
        expect(evidenceFor({ count: 483, heard_count: 1911, confirmed_count: 2 }, audioOn)).toBe('confirmed');
    });

    it('counts a species heard in the same window as seen and heard', () => {
        expect(evidenceFor({ count: 61, heard_count: 3850, confirmed_count: 0 }, audioOn)).toBe('seen_and_heard');
    });

    it('calls a species the camera alone reported camera only when BirdNET was listening', () => {
        expect(evidenceFor({ count: 5, heard_count: 0, confirmed_count: 0 }, audioOn)).toBe('camera_only');
    });

    it('does not read silence as absence when BirdNET is off or failed to load', () => {
        expect(evidenceFor({ count: 5, heard_count: 0, confirmed_count: 0 }, audioOff)).toBe('unconfirmed');
    });

    it('states unknown when the route did not report confirmations', () => {
        expect(evidenceFor({ count: 5, heard_count: 0 }, audioOn)).toBe('unknown');
        expect(evidenceFor({ count: 5, heard_count: 0, confirmed_count: null }, audioOff)).toBe('unknown');
    });

    it('still credits a call when confirmations are unknown', () => {
        expect(evidenceFor({ count: 5, heard_count: 3 }, audioOn)).toBe('seen_and_heard');
    });

    it('marks a species the camera never saw as heard only', () => {
        expect(evidenceFor({ count: 0, heard_count: 40, audio_only: true }, audioOn)).toBe('heard_only');
    });
});

describe('isCorroborated', () => {
    it('is true only when something besides the camera stands behind the row', () => {
        expect(isCorroborated('confirmed')).toBe(true);
        expect(isCorroborated('seen_and_heard')).toBe(true);
        expect(isCorroborated('heard_only')).toBe(true);
        expect(isCorroborated('camera_only')).toBe(false);
        expect(isCorroborated('unconfirmed')).toBe(false);
        expect(isCorroborated('unknown')).toBe(false);
    });
});
