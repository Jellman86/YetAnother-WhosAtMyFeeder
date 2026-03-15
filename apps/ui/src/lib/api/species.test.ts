import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock } = vi.hoisted(() => ({
    apiFetchMock: vi.fn()
}));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    handleResponse: vi.fn()
}));

import { exportEbirdCsv } from './species';

describe('exportEbirdCsv', () => {
    beforeEach(() => {
        apiFetchMock.mockReset();
        apiFetchMock.mockResolvedValue({
            ok: true,
            blob: vi.fn().mockResolvedValue(new Blob(['csv']))
        });

        vi.stubGlobal('URL', {
            createObjectURL: vi.fn(() => 'blob:test'),
            revokeObjectURL: vi.fn()
        });
        vi.stubGlobal('window', {
            URL: {
                createObjectURL: vi.fn(() => 'blob:test'),
                revokeObjectURL: vi.fn()
            }
        });
        vi.stubGlobal('document', {
            createElement: vi.fn(() => ({
                href: '',
                download: '',
                click: vi.fn()
            })),
            body: {
                appendChild: vi.fn(),
                removeChild: vi.fn()
            }
        });
    });

    it('requests range-scoped export when from and to dates are provided', async () => {
        await exportEbirdCsv({ from: '2026-03-12', to: '2026-03-14' });

        expect(apiFetchMock).toHaveBeenCalledWith('/api/ebird/export?from=2026-03-12&to=2026-03-14');
    });

    it('requests open-ended export when only from is provided', async () => {
        await exportEbirdCsv({ from: '2026-03-12' });

        expect(apiFetchMock).toHaveBeenCalledWith('/api/ebird/export?from=2026-03-12');
    });

    it('requests open-ended export when only to is provided', async () => {
        await exportEbirdCsv({ to: '2026-03-14' });

        expect(apiFetchMock).toHaveBeenCalledWith('/api/ebird/export?to=2026-03-14');
    });

    it('requests full export when no date is provided', async () => {
        await exportEbirdCsv();

        expect(apiFetchMock).toHaveBeenCalledWith('/api/ebird/export');
    });
});
