import { expect, test } from '@playwright/test';

test('a failed sign-in is announced, tied to its fields, and puts you back in the password', async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/status') {
            return route.fulfill({ json: { auth_required: true, public_access_enabled: false, is_authenticated: false, needs_initial_setup: false } });
        }
        if (path === '/api/auth/login') return route.fulfill({ status: 401, json: { detail: 'Invalid credentials' } });
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in login fixture' } });
    });
    await page.route('**/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/');

    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
    await expect(page.getByText('Sign in to manage your feeder.')).toBeVisible();
    await expect(page.locator('h1')).toHaveCount(1);
    await expect(page).toHaveTitle('Sign in · YA-WAMF');
    // The logo is decoration beside the heading, so it is silent.
    await expect(page.locator('img[alt="Logo"]')).toHaveCount(0);

    const username = page.getByLabel('Username');
    const password = page.getByLabel('Password');
    await expect(username).not.toHaveAttribute('aria-invalid', 'true');
    await username.fill('owner');
    await password.fill('wrong');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();

    await expect(page.getByRole('alert').filter({ hasText: 'Invalid credentials' })).toHaveAttribute('id', 'login-error');
    await expect(password).toBeFocused();
    for (const field of [username, password]) {
        await expect(field).toHaveAttribute('aria-invalid', 'true');
        await expect(field).toHaveAttribute('aria-describedby', 'login-error');
    }
    await expect(password).toHaveAccessibleDescription('Invalid credentials');
});
