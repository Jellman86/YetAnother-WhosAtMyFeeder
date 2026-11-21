import { test, expect, type Page } from '@playwright/test';
import { openMoreOptions } from './settings-page-mock';

// The cooldown saves whole minutes, at least one. The field must show what will be saved, not what
// was typed: on leaving it, "0", "-5" or "2.5" become the minutes the save will carry.

type Settings = Record<string, unknown>;

async function openNotifications(page: Page): Promise<Settings[]> {
    const writes: Settings[] = [];
    let settings: Settings = {
        frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
        notifications_notification_cooldown_minutes: 10
    };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), async route => {
        const request = route.request();
        const path = new URL(request.url()).pathname;
        if (path === '/api/settings') {
            if (request.method() === 'POST') {
                const payload = request.postDataJSON() as Settings;
                writes.push(payload);
                settings = { ...settings, ...payload };
                return route.fulfill({ json: { status: 'ok' } });
            }
            return route.fulfill({ json: settings });
        }
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await page.getByRole('link', { name: 'Alerts', exact: true }).click();
    // The cooldown is under Alerts' More options.
    await openMoreOptions(page);
    return writes;
}

// Each case starts from the value the typing coerces to, the case where nothing else would redraw
// the field: from 1, typing "0" still saves 1, and the field must say 1.
for (const [typed, shown] of [['0', '1'], ['-5', '1'], ['2.5', '2'], ['15', '15']] as const) {
    test(`a cooldown typed as "${typed}" shows and saves ${shown} minutes`, async ({ page }) => {
        const writes = await openNotifications(page);
        const minutes = page.locator('#notification-cooldown-minutes');
        await expect(minutes).toHaveValue('10');
        await minutes.fill(shown);
        await minutes.fill(typed);
        await minutes.blur();
        await expect(minutes).toHaveValue(shown);
        await page.getByRole('button', { name: 'Save changes', exact: true }).click();
        await expect.poll(() => writes.length).toBe(1);
        expect(writes[0].notifications_notification_cooldown_minutes).toBe(Number(shown));
    });
}
