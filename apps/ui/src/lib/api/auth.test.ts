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

    it('stores the owner token returned by password-enabled first-run setup', async () => {
        apiFetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                message: 'Setup completed successfully',
                access_token: 'owner-token',
                token_type: 'bearer',
                username: 'root',
                expires_in_hours: 168
            }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        );

        await setInitialPassword({
            username: 'root',
            password: 'password123',
            enableAuth: true
        });

        expect(setAuthTokenMock).toHaveBeenCalledWith('owner-token', 168);
    });

    it('does not invent an owner token when authentication is skipped', async () => {
        apiFetchMock.mockResolvedValue(
            new Response(JSON.stringify({
                message: 'Setup completed successfully',
                access_token: null,
                token_type: null,
                username: null,
                expires_in_hours: null
            }), { status: 200, headers: { 'Content-Type': 'application/json' } })
        );

        await setInitialPassword({
            username: 'root',
            password: null,
            enableAuth: false
        });

        expect(setAuthTokenMock).not.toHaveBeenCalled();
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
