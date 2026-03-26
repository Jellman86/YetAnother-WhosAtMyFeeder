import { describe, expect, it } from 'vitest';

import { handleResponse } from './core';

describe('handleResponse', () => {
    it('formats JSON validation errors into readable messages', async () => {
        const response = new Response(
            JSON.stringify({
                detail: [
                    {
                        type: 'missing',
                        loc: ['body', 'frigate_url'],
                        msg: 'Field required',
                    },
                    {
                        type: 'value_error',
                        loc: ['body', 'auth_password'],
                        msg: 'Value error, Password must contain at least one letter and one number',
                    }
                ]
            }),
            {
                status: 422,
                headers: { 'Content-Type': 'application/json' }
            }
        );

        await expect(handleResponse(response)).rejects.toThrow(
            'frigate_url: Field required; auth_password: Password must contain at least one letter and one number'
        );
    });
});
