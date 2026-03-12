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

    it('requests day-scoped export when a date is provided', async () => {
        await exportEbirdCsv('2026-03-12');

        expect(apiFetchMock).toHaveBeenCalledWith('/api/ebird/export?date=2026-03-12');
    });
});
