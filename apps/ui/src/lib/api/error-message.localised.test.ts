import { beforeAll, describe, expect, it } from 'vitest';
import { addMessages, init, locale } from 'svelte-i18n';

import deErrors from '../i18n/locales/de/errors.json';
import enErrors from '../i18n/locales/en/errors.json';
import { extractApiErrorMessage, isTransientGatewayError, readApiErrorMessage } from './error-message';

function response(status: number, body: string, contentType: string): Response {
    return new Response(body, { status, headers: { 'content-type': contentType } });
}

describe('errors a person reads are worded here, in their language', () => {
    beforeAll(async () => {
        addMessages('en', { errors: enErrors });
        addMessages('de', { errors: deErrors });
        await init({ fallbackLocale: 'en', initialLocale: 'en' });
    });

    it('never shows a raw plain-text server body', async () => {
        await locale.set('en');
        const message = await readApiErrorMessage(response(500, 'Internal Server Error', 'text/plain'), 'HTTP 500');
        expect(message).not.toContain('Internal Server Error');
        expect(message).toBe(enErrors.server_failure);
        // The cause is stated with a next step and where to look.
        expect(message).toMatch(/Try again/);
        expect(message).toMatch(/System health/);
    });

    it('explains a server failure that carries no reason, whatever its body type', async () => {
        await locale.set('en');
        expect(await readApiErrorMessage(response(502, '<html>Bad Gateway</html>', 'text/html'), 'HTTP 502')).toBe(enErrors.server_failure);
        expect(await readApiErrorMessage(response(500, '{}', 'application/json'), 'HTTP 500')).toBe(enErrors.server_failure);
        expect(await readApiErrorMessage(response(503, '', ''), 'HTTP 503')).toBe(enErrors.server_failure);
    });

    it('keeps a reason the server did give, and a caller’s own explanation', async () => {
        await locale.set('en');
        expect(await readApiErrorMessage(response(500, '{"detail":"The model file is missing."}', 'application/json'), 'HTTP 500')).toBe('The model file is missing.');
        // A caller that already says what failed keeps its words; the raw body is still never shown.
        expect(await readApiErrorMessage(response(500, 'Internal Server Error', 'text/plain'), 'Login failed')).toBe('Login failed');
        // Not a server failure: the status stays for the caller to interpret, without the raw body.
        expect(await readApiErrorMessage(response(404, 'Not Found', 'text/plain'), 'HTTP 404')).toBe('HTTP 404');
    });

    it('still knows a gateway failure is transient once its text is translated', () => {
        const error = Object.assign(new Error(enErrors.server_failure), { status: 502 });
        expect(isTransientGatewayError(error)).toBe(true);
        expect(isTransientGatewayError(Object.assign(new Error(enErrors.server_failure), { status: 500 }))).toBe(false);
        expect(isTransientGatewayError(new Error('HTTP 503'))).toBe(true);
    });

    it('words a failed connection test from its cause code, in German on a German page', async () => {
        const payload = { status: 'error', cause: 'host_not_found', service: 'mqtt', address: 'mqtt.invalid:1883', message: 'The host name in mqtt.invalid:1883 was not found. Check the address for the MQTT broker.' };
        await locale.set('de');
        const german = extractApiErrorMessage(payload, 'HTTP 502');
        expect(german).toContain('mqtt.invalid:1883');
        expect(german).toContain('MQTT-Broker');
        expect(german).toMatch(/nicht gefunden/);
        expect(german).not.toContain('was not found');
        expect(await readApiErrorMessage(response(500, 'Internal Server Error', 'text/plain'), 'HTTP 500')).toBe(deErrors.server_failure);
        await locale.set('en');
        expect(extractApiErrorMessage(payload, 'HTTP 502')).toBe('MQTT broker: the host name in mqtt.invalid:1883 was not found. Check the address.');
    });

    it('names the scheme as something to check when the address is a URL', async () => {
        await locale.set('en');
        const url = { cause: 'unreachable', service: 'birdnet', address: 'https://integration.example.test:8443', message: 'x' };
        expect(extractApiErrorMessage(url, 'HTTP 502')).toBe('BirdNET-Go: could not connect to https://integration.example.test:8443. Check the address, scheme and port.');
        expect(extractApiErrorMessage({ ...url, service: 'mqtt', address: 'mqtt.invalid:1883' }, 'HTTP 502')).toBe('MQTT broker: could not connect to mqtt.invalid:1883. Check the address and the port.');
    });

    it('falls back to the server’s sentence for a cause it does not know', async () => {
        await locale.set('de');
        expect(extractApiErrorMessage({ cause: 'something_new', service: 'mqtt', address: 'x', message: 'A new failure.' }, 'HTTP 502')).toBe('A new failure.');
        await locale.set('en');
    });
});
