import { describe, expect, it } from 'vitest';
import { rangeFieldError, settingsFieldErrors, standingFieldErrors } from './field-errors';

describe('a rejected save, put on its fields', () => {
    it('turns each validation error into plain words for its own field', () => {
        const errors = settingsFieldErrors([
            { type: 'value_error', loc: ['body', 'frigate_url'], msg: 'Value error, frigate_url must start with http:// or https://' },
            { type: 'less_than_equal', loc: ['body', 'mqtt_port'], msg: 'Input should be less than or equal to 65535', ctx: { le: 65535 } },
            { type: 'greater_than_equal', loc: ['body', 'audio_buffer_hours'], msg: 'Input should be greater than or equal to 1', ctx: { ge: 1 } },
            { type: 'int_parsing', loc: ['body', 'nest_dedupe_minutes'], msg: 'Input should be a valid integer' }
        ]);
        expect(errors).toEqual([
            expect.objectContaining({ field: 'frigate_url', key: 'settings.field_errors.frigate_url' }),
            expect.objectContaining({ field: 'mqtt_port', key: 'settings.field_errors.too_large', values: { limit: 65535 } }),
            expect.objectContaining({ field: 'audio_buffer_hours', key: 'settings.field_errors.too_small', values: { limit: 1 } }),
            expect.objectContaining({ field: 'nest_dedupe_minutes', key: 'settings.field_errors.whole_number' })
        ]);
        for (const error of errors) {
            expect(error.fallback).not.toMatch(/frigate_url|mqtt_port|Input should/);
        }
    });

    it('keeps the server reason, without its validator prefix, for a refusal it has no words for', () => {
        const [error] = settingsFieldErrors([{ type: 'value_error', loc: ['body', 'date_format'], msg: 'Value error, date_format must be one of: locale, mdy' }]);
        expect(error.key).toBe('settings.field_errors.refused');
        expect(error.values).toEqual({ reason: 'date_format must be one of: locale, mdy' });
    });

    it('ignores errors that name no field and keeps the first reason for a field', () => {
        expect(settingsFieldErrors('Internal Server Error')).toEqual([]);
        const errors = settingsFieldErrors([
            { type: 'missing', loc: [], msg: 'Field required' },
            { type: 'less_than_equal', loc: ['body', 'mqtt_port'], ctx: { le: 65535 } },
            { type: 'int_parsing', loc: ['body', 'mqtt_port'] }
        ]);
        expect(errors.map((error) => error.key)).toEqual(['settings.field_errors.too_large']);
    });

    it('withdraws an error once its field holds a different value than the one refused', () => {
        const errors = [rangeFieldError('recording_frame_delay_seconds', 1, 120), rangeFieldError('mqtt_port', 1, 65535)];
        const refused = { recording_frame_delay_seconds: 400, mqtt_port: 70000 };
        expect(standingFieldErrors(errors, refused, { recording_frame_delay_seconds: 12, mqtt_port: 70000 }).map((error) => error.field))
            .toEqual(['mqtt_port']);
    });
});
