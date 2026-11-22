import { test, expect, type Page } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// A channel's test passes only when the channel accepted the message. A send that was not
// delivered shows the failed step with its cause and the next step, in the page's language.
test.use({ viewport: { width: 1440, height: 900 } });

const WEBHOOK_SECRET = 'webhook-secret-value';

async function pressDiscordTest(page: Page, answer: { status: number; json: unknown }): Promise<void> {
    await openSettings(page, {
        notifications_discord_enabled: true,
        notifications_discord_webhook_url: '***REDACTED***'
    }, {
        route: '/settings/notifications',
        respond: (path, method) => (path === '/api/settings/notifications/test' && method === 'POST' ? answer : undefined)
    });
    await page.getByRole('button', { name: 'Send test notification', exact: true }).first().click();
    await expect(page.getByRole('dialog', { name: 'Notification test' })).toBeVisible();
}

const notDelivered = {
    status: 502,
    json: {
        status: 'error', cause: 'no_answer', channel: 'discord',
        message: `server sentence that must not be shown, ${WEBHOOK_SECRET}`
    }
};

test('a test message that was not delivered fails its step with the cause and the next step', async ({ page }) => {
    await pressDiscordTest(page, notDelivered);
    const dialog = page.getByRole('dialog', { name: 'Notification test' });
    const stage = dialog.locator('[data-diagnostic-stage-state]');
    await expect(stage).toHaveAttribute('data-diagnostic-stage-state', 'failed');
    await expect(stage).toHaveText('Failed');
    await expect(dialog.getByRole('listitem')).toContainText('Discord did not answer. Check the webhook address, then test again.');
    await expect(dialog).not.toContainText('Passed');
    await expect(dialog).not.toContainText('Test notification sent');
    await expect(dialog).not.toContainText(WEBHOOK_SECRET);
});

test('the failure reads in German on a German page', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await openSettings(page, { notifications_discord_enabled: true, notifications_discord_webhook_url: '***REDACTED***' }, {
        route: '/settings/notifications',
        respond: (path, method) => (path === '/api/settings/notifications/test' && method === 'POST' ? notDelivered : undefined)
    });
    await page.getByRole('button', { name: 'Testbenachrichtigung senden', exact: true }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.locator('[data-diagnostic-stage-state]')).toHaveAttribute('data-diagnostic-stage-state', 'failed');
    await expect(dialog.getByRole('listitem')).toContainText('Discord hat nicht geantwortet. Prüfen Sie die Webhook-URL und testen Sie dann erneut.');
});

test('a test message the channel accepted passes', async ({ page }) => {
    await pressDiscordTest(page, { status: 200, json: { status: 'ok', message: 'Test notification sent to discord' } });
    const dialog = page.getByRole('dialog', { name: 'Notification test' });
    await expect(dialog.locator('[data-diagnostic-stage-state]')).toHaveAttribute('data-diagnostic-stage-state', 'passed');
    // The pass is worded by the page, in its language, not by the server's English sentence.
    await expect(dialog.getByRole('listitem')).toContainText('Discord accepted the test message.');
    await expect(dialog).not.toContainText('Test notification sent to discord');
});

test('a pass reads in German on a German page', async ({ page }) => {
    await page.addInitScript(() => localStorage.setItem('preferred-language', 'de'));
    await openSettings(page, { notifications_discord_enabled: true, notifications_discord_webhook_url: '***REDACTED***' }, {
        route: '/settings/notifications',
        respond: (path, method) => (path === '/api/settings/notifications/test' && method === 'POST'
            ? { status: 200, json: { status: 'ok', message: 'Test notification sent to discord' } }
            : undefined)
    });
    await page.getByRole('button', { name: 'Testbenachrichtigung senden', exact: true }).first().click();
    const dialog = page.getByRole('dialog');
    await expect(dialog.getByRole('listitem')).toContainText('Discord hat die Testnachricht angenommen.');
    await expect(dialog).not.toContainText('Test notification sent');
});
