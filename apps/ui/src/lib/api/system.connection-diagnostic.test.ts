import { afterEach, describe, expect, it, vi } from 'vitest';

import { testFrigateConnection } from './system';

describe('Frigate connection diagnostic overrides', () => {
    afterEach(() => {
        vi.unstubAllGlobals();
    });

    it('tests the Frigate URL currently on screen', async () => {
        const fetchMock = vi.fn(async () => new Response(JSON.stringify({
            status: 'ok',
            frigate_url: 'http://edited-frigate:5000',
            version: '0.16.0'
        })));
        vi.stubGlobal('fetch', fetchMock);

        await testFrigateConnection('http://edited-frigate:5000');

        const request = fetchMock.mock.calls[0] as unknown as [string, RequestInit?];
        const requestUrl = String(request[0]);
        expect(requestUrl).toContain('/frigate/test?');
        expect(requestUrl).toContain('url=http%3A%2F%2Fedited-frigate%3A5000');
    });
});
