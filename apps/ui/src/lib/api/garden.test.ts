import { afterEach, describe, expect, it, vi } from 'vitest';
import { setApiKey, setAuthToken } from './core';
import { identifyGarden } from './garden';

afterEach(() => {
    setAuthToken(null);
    setApiKey(null);
    vi.unstubAllGlobals();
});

describe('garden species suggestion requests', () => {
    it('delivers a JSON request to the owner-only endpoint', async () => {
        setAuthToken('owner-session');
        let received: Request | undefined;
        vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
            received = new Request(`http://localhost${url}`, options);
            return new Response('{}', { headers: { 'Content-Type': 'application/json' } });
        }));

        await identifyGarden('capture 1', { variant: '4.0.3b', provider: 'intel_npu' });

        expect(received?.url).toBe('http://localhost/api/garden/capture%201/identify');
        expect(received?.method).toBe('POST');
        expect(received?.headers.get('Authorization')).toBe('Bearer owner-session');
        expect(received?.headers.get('Content-Type')).toBe('application/json');
        expect(await received?.json()).toEqual({ variant: '4.0.3b', provider: 'intel_npu' });
    });
});

describe('advisory garden photo checks', () => {
    it('binds an explicit request to the displayed photo and selected provider', async () => {
        const { checkGardenPhoto } = await import('./garden');
        setAuthToken('owner-session');
        let received: Request | undefined;
        vi.stubGlobal('fetch', vi.fn(async (url: string, options: RequestInit) => {
            received = new Request(`http://localhost${url}`, options);
            return new Response('{}', { headers: { 'Content-Type': 'application/json' } });
        }));
        const controller = new AbortController();
        await checkGardenPhoto('capture 1', { image_sha256: 'a'.repeat(64), provider: 'intel_npu' }, controller.signal);
        expect(received?.url).toBe('http://localhost/api/garden/capture%201/check-photo');
        expect(received?.headers.get('Authorization')).toBe('Bearer owner-session');
        expect(received?.headers.get('Content-Type')).toBe('application/json');
        expect(await received?.json()).toEqual({ image_sha256: 'a'.repeat(64), provider: 'intel_npu' });
    });
});

describe('garden Explorer timeline requests', () => {
    it('asks for one window, camera and order, and leaves out what was not chosen', async () => {
        const { fetchGardenTimeline } = await import('./garden');
        setAuthToken('owner-session');
        const urls: string[] = [];
        vi.stubGlobal('fetch', vi.fn(async (url: string) => {
            urls.push(url);
            return new Response('{"items":[],"total":0,"limit":200,"offset":0}', { headers: { 'Content-Type': 'application/json' } });
        }));
        await fetchGardenTimeline({ start: '2026-10-13T00:00:00.000Z', end: '2026-10-14T00:00:00.000Z', camera: 'patio', order: 'oldest', limit: 200 });
        await fetchGardenTimeline({ start: null, order: 'newest', limit: 24, offset: 48 });
        const [windowed, open] = urls.map((url) => new URL(url, 'http://localhost'));
        expect(windowed.pathname).toBe('/api/garden/timeline');
        expect(Object.fromEntries(windowed.searchParams)).toEqual({
            order: 'oldest', limit: '200', offset: '0',
            start: '2026-10-13T00:00:00.000Z', end: '2026-10-14T00:00:00.000Z', camera: 'patio'
        });
        expect(Object.fromEntries(open.searchParams)).toEqual({ order: 'newest', limit: '24', offset: '48' });
    });
});
