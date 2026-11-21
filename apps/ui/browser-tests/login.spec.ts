import { expect, test, type Page } from '@playwright/test';

const SIGN_IN_REQUIRED = { auth_required: true, public_access_enabled: false, is_authenticated: false, needs_initial_setup: false };

async function openSignIn(page: Page, login: { status: number; json: unknown } | 'unreachable'): Promise<{ attempts: () => number }> {
    let attempts = 0;
    await page.route(url => url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/auth/status') return route.fulfill({ json: SIGN_IN_REQUIRED });
        if (path === '/api/auth/login') {
            attempts += 1;
            return login === 'unreachable' ? route.abort('connectionrefused') : route.fulfill(login);
        }
        return route.fulfill({ status: 503, json: { detail: 'Unavailable in login fixture' } });
    });
    await page.route(url => url.pathname === '/health', route => route.fulfill({ json: { status: 'healthy' } }));
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('/');
    await expect(page.getByRole('heading', { level: 1, name: 'Sign in' })).toBeVisible();
    return { attempts: () => attempts };
}

const WRONG_CREDENTIALS = 'That username or password is not right. Check both and try again. Passwords are case sensitive.';

test('a failed sign-in is announced, tied to its fields, and puts you back in the password', async ({ page }) => {
    await openSignIn(page, { status: 401, json: { detail: 'Invalid credentials' } });

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

    // The message says what went wrong and what to do, not the server's two-word code.
    await expect(page.getByRole('alert').filter({ hasText: WRONG_CREDENTIALS })).toHaveAttribute('id', 'login-error');
    await expect(page.getByText('Invalid credentials')).toHaveCount(0);
    await expect(password).toBeFocused();
    for (const field of [username, password]) {
        await expect(field).toHaveAttribute('aria-invalid', 'true');
        await expect(field).toHaveAttribute('aria-describedby', 'login-error');
    }
    await expect(password).toHaveAccessibleDescription(WRONG_CREDENTIALS);
});

test('an empty sign-in names each missing field beside it, in the page and not in a browser bubble', async ({ page }) => {
    const fixture = await openSignIn(page, { status: 401, json: { detail: 'Invalid credentials' } });
    const username = page.getByLabel('Username');
    const password = page.getByLabel('Password');
    // The browser's own "fill out this field" bubble is off: it is unstyled, untranslated by the
    // app, shows one field at a time and vanishes on its own.
    await expect(page.locator('form')).toHaveJSProperty('noValidate', true);
    for (const field of [username, password]) await expect(field).toHaveAttribute('aria-required', 'true');

    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.locator('#username-error')).toHaveText('Enter your username.');
    await expect(page.locator('#password-error')).toHaveText('Enter your password.');
    await expect(username).toBeFocused();
    await expect(username).toHaveAttribute('aria-invalid', 'true');
    await expect(username).toHaveAccessibleDescription('Enter your username.');
    await expect(password).toHaveAccessibleDescription('Enter your password.');
    // Nothing was sent, and the form did not move the fields when the messages arrived.
    expect(fixture.attempts()).toBe(0);

    // A message goes as soon as its field is filled in, and the other stays.
    await username.fill('owner');
    await expect(page.locator('#username-error')).toHaveCount(0);
    await expect(username).not.toHaveAttribute('aria-invalid', 'true');
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(password).toBeFocused();
    await expect(page.locator('#password-error')).toHaveText('Enter your password.');
    expect(fixture.attempts()).toBe(0);
});

for (const [name, login, message] of [
    ['too many attempts', { status: 429, json: { detail: 'Rate limit exceeded' } }, 'Too many sign-in attempts. Wait a minute, then try again.'],
    ['a server fault', { status: 500, json: { detail: 'Authentication not configured - please complete initial setup' } }, 'YA-WAMF could not check your sign-in. Try again in a moment. If it keeps happening, look at the container logs.'],
    ['no answer from the feeder', 'unreachable', 'Could not reach YA-WAMF. Check that it is running and that this device can reach it, then try again.']
] as const) {
    test(`a sign-in stopped by ${name} says the cause and the next step`, async ({ page }) => {
        await openSignIn(page, login);
        await page.getByLabel('Username').fill('owner');
        await page.getByLabel('Password').fill('correct horse');
        await page.getByRole('button', { name: 'Sign in', exact: true }).click();
        await expect(page.getByRole('alert').filter({ hasText: message })).toBeVisible();
        // Only a wrong username or password marks the fields as the thing to fix.
        await expect(page.getByLabel('Password')).not.toHaveAttribute('aria-invalid', 'true');
    });
}

const BOTH_MISSING = 'Enter your username. Enter your password.';

/** Record, at each moment a screen reader would speak, what it would have to speak from. */
async function recordAnnouncements(page: Page): Promise<void> {
    await page.evaluate(() => {
        const log: string[] = [];
        (window as unknown as { announcements: string[] }).announcements = log;
        const summary = document.querySelector('[data-login-validation-summary]');
        if (!summary) throw new Error('No validation summary region');
        new MutationObserver(() => log.push(`summary:${summary.textContent?.trim() ?? ''}`)).observe(summary, { childList: true, characterData: true, subtree: true });
        document.addEventListener('focusin', (event) => {
            const field = event.target as HTMLElement;
            if (field.tagName !== 'INPUT') return;
            const described = field.getAttribute('aria-describedby');
            const description = described ? document.getElementById(described)?.textContent?.trim() ?? 'MISSING' : 'none';
            log.push(`focus:${field.id}:${field.getAttribute('aria-invalid') ?? 'valid'}:${description}:summary=${summary.textContent?.trim() ?? ''}`);
        });
    });
}
const announcements = (page: Page): Promise<string[]> => page.evaluate(() => (window as unknown as { announcements: string[] }).announcements.splice(0));

test('a missing field is announced once per submit: by its field when focus moves, by a live region when it cannot', async ({ page }) => {
    const fixture = await openSignIn(page, { status: 401, json: { detail: 'Invalid credentials' } });
    const username = page.getByLabel('Username');
    const password = page.getByLabel('Password');
    const summary = page.locator('[data-login-validation-summary]');
    // One polite live region, in the page from the start so that text landing in it is announced,
    // and empty until there is something to say.
    await expect(summary).toHaveCount(1);
    await expect(summary).toHaveAttribute('role', 'status');
    await expect(summary).toHaveText('');
    // The form has this region for validation and the alert for a refused sign-in, and no third.
    await expect(page.locator('form').locator('[aria-live], [role="status"], [role="alert"]')).toHaveCount(2);
    await recordAnnouncements(page);

    // Focus is already in the empty username: nothing moves, so the summary speaks.
    await username.focus();
    await announcements(page);
    await page.keyboard.press('Enter');
    await expect(summary).toHaveText(BOTH_MISSING);
    await expect(username).toBeFocused();
    await expect(username).toHaveAccessibleDescription('Enter your username.');
    expect(await announcements(page)).toEqual([`summary:${BOTH_MISSING}`]);

    // The same submit again is a new announcement: the region is emptied, then filled.
    await page.keyboard.press('Enter');
    await expect(summary).toHaveText(BOTH_MISSING);
    expect(await announcements(page)).toEqual(['summary:', `summary:${BOTH_MISSING}`]);

    // Focus moves to the field at fault: its message is already tied to it when focus lands,
    // and the summary stays silent so the message is not heard twice.
    await username.fill('owner');
    await announcements(page);
    await page.keyboard.press('Enter');
    await expect(password).toBeFocused();
    await expect(summary).toHaveText('');
    expect(await announcements(page)).toEqual(['summary:', 'focus:password:true:Enter your password.:summary=']);

    // From the button, focus moves to the first field at fault, described before it is focused.
    await username.fill('');
    await page.getByRole('button', { name: 'Sign in', exact: true }).focus();
    await announcements(page);
    await page.keyboard.press('Enter');
    await expect(username).toBeFocused();
    expect(await announcements(page)).toEqual(['focus:username:true:Enter your username.:summary=']);

    // A refused sign-in is the alert's to announce, not the summary's.
    await username.fill('owner');
    await password.fill('wrong');
    await announcements(page);
    await page.keyboard.press('Enter');
    await expect(page.getByRole('alert').filter({ hasText: WRONG_CREDENTIALS })).toBeVisible();
    await expect(summary).toHaveText('');
    expect(fixture.attempts()).toBe(1);
});
