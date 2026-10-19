import { afterEach, expect, it, vi } from 'vitest';
import { prepareNativeProfileRevalidation, uploadNativeProfileInputs, cancelNativeProfileRevalidation } from './native-profile';

afterEach(() => vi.unstubAllGlobals());

it('prepares a known attempt before sending private multipart inputs without a JSON content type', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetcher);
    await prepareNativeProfileRevalidation('fingerprint', 'known-attempt');
    const [, options] = fetcher.mock.calls[0];
    expect(JSON.parse(options.body)).toEqual({ profile_fingerprint: 'fingerprint', attempt_id: 'known-attempt' });
    fetcher.mockResolvedValue(new Response('{}', { status: 200 }));
    await uploadNativeProfileInputs('known-attempt', [new File(['one'], 'one.jpg')], new File(['clip'], 'clip.mp4'));
    const [url, upload] = fetcher.mock.calls[1];
    expect(url).toContain('/known-attempt/inputs');
    expect(upload.body).toBeInstanceOf(FormData);
    expect(upload.headers['Content-Type']).toBeUndefined();
});

it('cancels the known reservation without replaying an upload', async () => {
    const fetcher = vi.fn().mockResolvedValue(new Response('{}', { status: 200 }));
    vi.stubGlobal('fetch', fetcher);
    await cancelNativeProfileRevalidation('known-attempt');
    expect(fetcher).toHaveBeenCalledOnce();
    expect(fetcher.mock.calls[0][0]).toContain('/known-attempt/cancel');
});
