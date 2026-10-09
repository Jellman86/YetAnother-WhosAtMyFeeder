import { afterEach, describe, expect, it, vi } from 'vitest';
import { setApiKey, setAuthToken } from './core';
import { fetchModelEvalArtifact } from './model_eval';

afterEach(() => {
    setAuthToken(null);
    setApiKey(null);
    vi.unstubAllGlobals();
});

describe('model evaluation artifact downloads', () => {
    it.each(['summary.json', 'runtime.json', 'confusions.csv'])('sends the owner session for %s in a header', async (artifact) => {
        setAuthToken('owner-session');
        const fetch = vi.fn().mockResolvedValue(new Response('artifact contents'));
        vi.stubGlobal('fetch', fetch);

        const blob = await fetchModelEvalArtifact('run 1', artifact);

        expect(await blob.text()).toBe('artifact contents');
        expect(fetch).toHaveBeenCalledWith(`/api/diagnostics/model-eval/runs/run%201/${artifact}`, expect.objectContaining({
            headers: expect.objectContaining({ Authorization: 'Bearer owner-session' })
        }));
        expect(fetch.mock.calls[0][0]).not.toContain('owner-session');
    });

    it('retains support for installations using an API key', async () => {
        setApiKey('owner-key');
        const fetch = vi.fn().mockResolvedValue(new Response('{}'));
        vi.stubGlobal('fetch', fetch);
        await fetchModelEvalArtifact('run', 'summary.json');
        expect(fetch.mock.calls[0][1].headers['X-API-Key']).toBe('owner-key');
        expect(fetch.mock.calls[0][0]).not.toContain('owner-key');
    });

    it.each([403, 404])('reports HTTP %s instead of downloading an error as a file', async (status) => {
        vi.stubGlobal('fetch', vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Download denied' }), {
            status, headers: { 'Content-Type': 'application/json' }
        })));
        await expect(fetchModelEvalArtifact('run', 'summary.json')).rejects.toMatchObject({ status, message: 'Download denied' });
    });
});
