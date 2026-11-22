import { test, expect } from '@playwright/test';
import { openMoreOptions } from './settings-page-mock';

// Each Notification option is a row holding its radio; the whole row shows where keyboard
// focus is (WCAG 2.4.7). The ring follows :focus-visible, so the test arrives by keyboard.
test('the notification option tiles show keyboard focus', async ({ page }) => {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/settings') {
            return route.fulfill({ json: {
                frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
                notifications_link_target: 'yawamf', notifications_filter_species_mode: 'none'
            } });
        }
        if (path.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (path.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (path.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await page.getByRole('link', { name: 'Notifications', exact: true }).click();
    // The link and species choices are under Notifications' More options.
    await openMoreOptions(page);

    for (const group of ['notification-link-target', 'notification-species-filter-mode']) {
        const tile = page.locator('label', { has: page.locator(`input[name="${group}"]`) }).first();
        const radio = tile.locator('input');
        await expect(tile).toHaveCSS('box-shadow', 'none');
        await radio.focus();
        await page.keyboard.press('Shift+Tab');
        await page.keyboard.press('Tab');
        await expect(radio).toBeFocused();
        await expect(tile).not.toHaveCSS('box-shadow', 'none');
    }
});
