import { test, expect } from '@playwright/test';

// Settings that could not be read must not be offered for editing: a form of defaults or of an
// older copy looks current, and applying it would overwrite the configuration the backend holds.
test('a failed settings read shows the reason and a retry, never an editable form, and the retry recovers', async ({ page }) => {
    let settingsAvailable = false;
    let settingsReads = 0;
    const saves: unknown[] = [];
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings' && request.method() === 'POST') {
            saves.push(request.postDataJSON());
            return route.fulfill({ json: { status: 'updated' } });
        }
        if (path === '/api/settings') {
            settingsReads += 1;
            if (!settingsAvailable) return route.fulfill({ status: 503, json: { detail: 'Service unavailable' } });
            return route.fulfill({ json: { frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false } });
        }
        if (path === '/api/models/installed' || path === '/api/models/available') return route.fulfill({ json: [] });
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');

    const failure = page.getByRole('alert').filter({ hasText: 'Your settings could not be read' });
    await expect(failure).toBeVisible();
    await expect(failure).toContainText('nothing is shown for editing');
    await expect(page.locator('#mqtt-server')).toHaveCount(0);
    await expect(page.locator('main input, main select, main textarea')).toHaveCount(0);
    await expect(page.getByRole('button', { name: 'Save changes', exact: true })).toHaveCount(0);

    const readsBeforeRetry = settingsReads;
    await failure.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(failure).toBeVisible();
    expect(settingsReads).toBeGreaterThan(readsBeforeRetry);

    settingsAvailable = true;
    await failure.getByRole('button', { name: 'Try again', exact: true }).click();
    await expect(page.locator('#mqtt-server')).toHaveValue('mqtt');
    await expect(failure).toHaveCount(0);
    expect(saves).toEqual([]);
});
