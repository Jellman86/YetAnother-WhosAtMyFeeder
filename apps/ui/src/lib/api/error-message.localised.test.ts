import { beforeAll, describe, expect, it } from 'vitest';
import { addMessages, init, locale } from 'svelte-i18n';

import deErrors from '../i18n/locales/de/errors.json';
import enErrors from '../i18n/locales/en/errors.json';
import { connectionCauseMessage, extractApiErrorMessage, isTransientGatewayError, readApiErrorMessage } from './error-message';

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
        expect(message).toMatch(/open Health/);
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

    it('words a broker failure from its cause code, for Health as for the connection test', async () => {
        await locale.set('en');
        expect(connectionCauseMessage('host_not_found', 'mqtt', 'mqtt.invalid:1883')).toBe(
            'MQTT broker: the host name in mqtt.invalid:1883 was not found. Check the address.'
        );
        expect(connectionCauseMessage('something_else', 'mqtt', 'mqtt.invalid:1883')).toBeNull();
        await locale.set('de');
        expect(connectionCauseMessage('host_not_found', 'mqtt', 'mqtt.invalid:1883')).not.toContain('was not found');
    });

    it('words a channel test that was not delivered from its cause code, never from the server’s English', async () => {
        const payload = { status: 'error', cause: 'no_answer', channel: 'discord', message: 'Discord did not answer. Check the webhook address, then test again.' };
        await locale.set('en');
        expect(extractApiErrorMessage(payload, 'HTTP 502')).toBe('Discord did not answer. Check the webhook address, then test again.');
        expect(extractApiErrorMessage({ ...payload, channel: 'telegram' }, 'HTTP 502')).toBe(
            'Telegram did not answer. Check that YA-WAMF can reach the internet, then test again.'
        );
        expect(extractApiErrorMessage({ ...payload, cause: 'refused', channel: 'pushover' }, 'HTTP 502')).toBe(
            'Pushover refused the message. Check the user key and API token, then test again.'
        );
        await locale.set('de');
        const german = extractApiErrorMessage(payload, 'HTTP 502');
        expect(german).toContain('Discord');
        expect(german).not.toContain('did not answer');
        expect(german).toMatch(/Prüfen Sie/);
        await locale.set('en');
    });

    it('has a sentence with a next step for every cause on every channel', async () => {
        await locale.set('en');
        for (const channel of ['discord', 'pushover', 'telegram']) {
            for (const cause of ['not_configured', 'no_answer', 'timeout', 'refused', 'unexpected_reply', 'rate_limited', 'provider_error']) {
                const sentence = extractApiErrorMessage({ cause, channel, message: 'server sentence' }, 'HTTP 502');
                expect(sentence, `${channel} ${cause}`).not.toBe('server sentence');
                expect(sentence, `${channel} ${cause}`).toMatch(/then test again\.$/);
            }
        }
    });

    it('names the fields a channel is missing, and a reply that came from something in between', async () => {
        await locale.set('en');
        const missing = { cause: 'not_configured', message: 'server sentence' };
        expect(extractApiErrorMessage({ ...missing, channel: 'discord' }, 'HTTP 400')).toBe('Discord is not set up yet. Enter the webhook address, then test again.');
        expect(extractApiErrorMessage({ ...missing, channel: 'pushover' }, 'HTTP 400')).toBe('Pushover is not set up yet. Enter the user key and API token, then test again.');
        expect(extractApiErrorMessage({ ...missing, channel: 'telegram' }, 'HTTP 400')).toBe('Telegram is not set up yet. Enter the bot token and chat ID, then test again.');
        expect(extractApiErrorMessage({ cause: 'unexpected_reply', channel: 'telegram', message: 'server sentence' }, 'HTTP 502')).toBe(
            'Something answered in place of Telegram. Check for a proxy or sign-in page between YA-WAMF and the internet, then test again.'
        );
    });

    it('falls back to the server’s sentence for a delivery cause or channel it does not know', async () => {
        await locale.set('en');
        expect(extractApiErrorMessage({ cause: 'something_new', channel: 'discord', message: 'A new failure.' }, 'HTTP 502')).toBe('A new failure.');
        expect(extractApiErrorMessage({ cause: 'refused', channel: 'carrier_pigeon', message: 'A new channel.' }, 'HTTP 502')).toBe('A new channel.');
    });
});
