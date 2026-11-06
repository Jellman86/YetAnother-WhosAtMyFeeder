import { describe, expect, it } from 'vitest';
import { dayBarSlots } from './day-bar';

describe('dayBarSlots', () => {
    it('holds the audio figures from configuration, before any call has been read', () => {
        expect(dayBarSlots({ audioConfigured: true, countingConfigured: false, countedCaptures: null }).audio).toBe(true);
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: false, countedCaptures: null }).audio).toBe(false);
    });

    it('holds the counted-birds figure while the day is read when counting is configured', () => {
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: true, countedCaptures: null }).countedBirds).toBe(true);
        // Configured but nothing analysed yet: the figure stays and says so, rather than leaving.
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: true, countedCaptures: 0 }).countedBirds).toBe(true);
    });

    it('leaves the counted-birds figure out when counting is off and the window holds no counts', () => {
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: false, countedCaptures: null }).countedBirds).toBe(false);
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: false, countedCaptures: 0 }).countedBirds).toBe(false);
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: null, countedCaptures: null }).countedBirds).toBe(false);
    });

    it('still shows counts the window holds after counting was turned off', () => {
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: false, countedCaptures: 3 }).countedBirds).toBe(true);
        expect(dayBarSlots({ audioConfigured: false, countingConfigured: null, countedCaptures: 3 }).countedBirds).toBe(true);
    });
});
