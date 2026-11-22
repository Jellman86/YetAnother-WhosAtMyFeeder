import { describe, expect, it } from 'vitest';
import { serviceState } from './service-state';
import { serviceTests } from './service-tests.svelte';

describe('integration tests kept for the visit', () => {
    it('has nothing to say about a service that was never tested', () => {
        expect(serviceTests.last('ha_weather')).toBeNull();
    });

    it('keeps the last result of each service apart, with its time, reason and the values it ran with', () => {
        serviceTests.record('birdweather', { passed: false, message: 'The token was refused.' }, 'token-a', 1000);
        serviceTests.record('ai', { passed: true, message: '' }, 'gemini|model|key', 2000);
        expect(serviceTests.last('birdweather')).toEqual({ passed: false, message: 'The token was refused.', at: 1000, signature: 'token-a' });
        expect(serviceTests.last('ai')?.passed).toBe(true);
        serviceTests.record('birdweather', { passed: true, message: '' }, 'token-b', 3000);
        expect(serviceTests.last('birdweather')).toEqual({ passed: true, message: '', at: 3000, signature: 'token-b' });
    });

    it('still describes the card after it is drawn again, until a value it ran with changes', () => {
        serviceTests.record('birdnet', { passed: true, message: '' }, 'url|topic', 4000);
        const reading = { enabled: true, missing: null, test: serviceTests.last('birdnet') };
        expect(serviceState({ ...reading, signature: 'url|topic' })).toEqual({ kind: 'passed', at: 4000 });
        expect(serviceState({ ...reading, signature: 'other|topic' })).toEqual({ kind: 'not_tested' });
    });
});
