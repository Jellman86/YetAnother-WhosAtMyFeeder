import { describe, expect, it } from 'vitest';
import { healthNotificationCause } from './health-notification';

describe('healthNotificationCause', () => {
    it('names the broker first, because nothing arrives without it', () => {
        expect(healthNotificationCause({ mqtt: { connection_state: 'disconnected' }, frigate_api: { state: 'unreachable' } })).toBe('mqtt_down');
        expect(healthNotificationCause({ mqtt: { connection_state: 'not_configured' } })).toBe('mqtt_not_configured');
    });

    it('names Frigate when only Frigate is not answering', () => {
        expect(healthNotificationCause({ mqtt: { connection_state: 'connected' }, frigate_api: { state: 'unreachable' } })).toBe('frigate_down');
    });

    it('says a critical pipeline failure when one is active', () => {
        expect(healthNotificationCause({ mqtt: { connection_state: 'connected' }, event_pipeline: { critical_failure_active: true } })).toBe('pipeline_critical');
    });

    it('falls back to pointing at Health when the cause is not one it can name', () => {
        expect(healthNotificationCause({ status: 'degraded' })).toBe('other');
        expect(healthNotificationCause(null)).toBe('other');
    });
});
