import { describe, expect, it } from 'vitest';

import {
    formatIlluminance,
    illuminanceStepOutcome,
    isHomeAssistantEntityId,
    type IlluminanceStepText
} from './illuminance';

const text: IlluminanceStepText = {
    measured: ({ reading, entity }) => `${reading} measured by ${entity}.`,
    missing: {
        invalid_entity_id: ({ entity }) => `${entity} is not an entity id.`,
        unreachable: ({ entity }) => `Home Assistant did not return ${entity}.`,
        not_illuminance: ({ entity }) => `${entity} is not an illuminance sensor.`,
        unavailable: ({ entity }) => `${entity} has no reading right now.`,
        not_numeric: ({ entity }) => `${entity} did not report a number.`,
        out_of_range: ({ entity }) => `${entity} reported a value outside 0 to 200,000 lx.`
    },
    noAnswer: 'The test returned no light reading.'
};

describe('a stored light level reads as lux', () => {
    it('groups thousands and drops needless decimals', () => {
        expect(formatIlluminance(1240.5, 'en-GB')).toBe('1,241 lx');
        expect(formatIlluminance(88, 'en-GB')).toBe('88 lx');
        expect(formatIlluminance(120000, 'en-GB')).toBe('120,000 lx');
    });

    it('keeps one decimal in the dark, where it matters', () => {
        expect(formatIlluminance(0.42, 'en-GB')).toBe('0.4 lx');
        expect(formatIlluminance(9.96, 'en-GB')).toBe('10 lx');
        expect(formatIlluminance(0, 'en-GB')).toBe('0 lx');
    });

    it('follows the reader\'s number format', () => {
        expect(formatIlluminance(1240, 'de-DE')).toBe('1.240 lx');
    });

    it('says nothing when no light level was measured', () => {
        for (const missing of [undefined, null, Number.NaN, Number.POSITIVE_INFINITY, -1]) {
            expect(formatIlluminance(missing, 'en-GB')).toBeNull();
        }
    });
});

describe('the settings field accepts only an entity id', () => {
    it('recognises Home Assistant entity ids', () => {
        expect(isHomeAssistantEntityId('sensor.feeder_illuminance')).toBe(true);
        expect(isHomeAssistantEntityId('  sensor.lux_2 ')).toBe(true);
    });

    it('rejects anything else', () => {
        for (const value of ['feeder illuminance', 'sensor.', 'Sensor.Feeder', 'sensor/../config', 'sensor.a?b=1']) {
            expect(isHomeAssistantEntityId(value)).toBe(false);
        }
    });
});

describe('the live test states the measured value or why it is missing', () => {
    it('passes with the measured value', () => {
        expect(
            illuminanceStepOutcome({ entity_id: 'sensor.feeder_lux', status: 'ok', lux: 1240.5, reason: null }, text, 'en-GB')
        ).toEqual({ status: 'ok', message: '1,241 lx measured by sensor.feeder_lux.' });
    });

    it('fails with the reason in words', () => {
        const reasons = ['invalid_entity_id', 'unreachable', 'not_illuminance', 'unavailable', 'not_numeric', 'out_of_range'] as const;
        for (const reason of reasons) {
            const outcome = illuminanceStepOutcome({ entity_id: 'sensor.x', status: 'error', lux: null, reason }, text, 'en-GB');
            expect(outcome.status).toBe('error');
            expect(outcome.message).toBe(text.missing[reason]({ entity: 'sensor.x' }));
        }
    });

    it('never passes without a measured value', () => {
        expect(illuminanceStepOutcome(null, text, 'en-GB')).toEqual({ status: 'error', message: text.noAnswer });
        expect(illuminanceStepOutcome(undefined, text, 'en-GB')).toEqual({ status: 'error', message: text.noAnswer });
        expect(
            illuminanceStepOutcome({ entity_id: 'sensor.x', status: 'ok', lux: null, reason: null }, text, 'en-GB')
        ).toEqual({ status: 'error', message: text.noAnswer });
        expect(
            illuminanceStepOutcome({ entity_id: 'sensor.x', status: 'error', lux: 12, reason: null }, text, 'en-GB')
        ).toEqual({ status: 'error', message: text.noAnswer });
    });
});
