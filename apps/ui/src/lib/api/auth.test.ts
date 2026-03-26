import { beforeEach, describe, expect, it, vi } from 'vitest';

const { apiFetchMock, getHeadersMock, setAuthTokenMock } = vi.hoisted(() => ({
    apiFetchMock: vi.fn(),
    getHeadersMock: vi.fn(() => ({})),
    setAuthTokenMock: vi.fn(),
}));

vi.mock('./core', () => ({
    API_BASE: '/api',
    apiFetch: apiFetchMock,
    getHeaders: getHeadersMock,
    setAuthToken: setAuthTokenMock,
}));

import { setInitialPassword } from './auth';

describe('setInitialPassword', () => {
    beforeEach(() => {
        apiFetchMock.mockReset();
        getHeadersMock.mockClear();
        setAuthTokenMock.mockClear();
    });

    it('surfaces readable validation errors from FastAPI detail arrays', async () => {
        apiFetchMock.mockResolvedValue(
            new Response(
                JSON.stringify({
                    detail: [
                        {
                            type: 'value_error',
                            loc: ['body', 'password'],
                            msg: 'Value error, Password must contain at least one letter and one number',
                        }
                    ]
                }),
                {
                    status: 422,
                    headers: { 'Content-Type': 'application/json' }
                }
            )
        );

        await expect(
            setInitialPassword({
                username: 'root',
                password: 'abcdefgh',
                enableAuth: true
            })
        ).rejects.toThrow('Password must contain at least one letter and one number');
    });
});
