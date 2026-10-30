import { test, expect, type Page } from '@playwright/test';

// Shortening history retention deletes detections at the next cleanup. The owner sees how
// many before saving, and is asked once more on Apply; cancelling saves nothing.
interface Fixture {
    savedRetention: number;
    automaticCleanup: boolean;
    saves: Record<string, unknown>[];
    previews: number[];
}

async function openDataSettings(page: Page, savedRetention: number, automaticCleanup = true): Promise<Fixture> {
    const fixture: Fixture = { savedRetention, automaticCleanup, saves: [], previews: [] };
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname === '/health' || url.pathname.startsWith('/api/'), route => {
        const request = route.request();
        const url = new URL(request.url());
        if (url.pathname === '/api/settings' && request.method() === 'POST') {
            const body = request.postDataJSON() as Record<string, unknown>;
            fixture.saves.push(body);
            if (typeof body.retention_days === 'number') fixture.savedRetention = body.retention_days;
            return route.fulfill({ json: { status: 'updated' } });
        }
        if (url.pathname === '/api/settings') {
            return route.fulfill({ json: {
                frigate_url: 'http://frigate:5000', mqtt_server: 'mqtt', mqtt_port: 1883, mqtt_auth: false,
                retention_days: fixture.savedRetention
            } });
        }
        if (url.pathname === '/api/maintenance/stats') {
            const preview = url.searchParams.get('retention_days');
            if (preview !== null) fixture.previews.push(Number(preview));
            return route.fulfill({ json: {
                total_detections: 120,
                oldest_detection: '2026-01-01T09:00:00',
                retention_days: fixture.savedRetention,
                detections_to_cleanup: 0,
                kept_newest_per_species: 3,
                automatic_cleanup: fixture.automaticCleanup,
                preview_retention_days: preview === null ? null : Number(preview),
                preview_detections_to_cleanup: preview === null ? null : Number(preview) === 7 ? 42 : 1
            } });
        }
        if (url.pathname.endsWith('/audio/sources')) return route.fulfill({ json: [] });
        if (url.pathname.endsWith('/frigate/config')) return route.fulfill({ json: { cameras: {} } });
        if (url.pathname.endsWith('/backfill/status')) return route.fulfill({ json: null });
        return route.fulfill({ json: {} });
    });
    await page.goto('/browser-tests/settings-backfill.html');
    await page.getByRole('link', { name: 'Data', exact: true }).click();
    await expect(page.locator('#retention-days')).toHaveValue(String(savedRetention));
    return fixture;
}

test('shrinking retention shows the count, and cancelling the confirmation saves nothing', async ({ page }, testInfo) => {
    const fixture = await openDataSettings(page, 30);
    const tiles = page.locator('.card-base.rounded-2xl.p-6.text-center');
    await expect(tiles.filter({ hasText: 'Retention' })).toContainText('30');
    await expect(tiles.filter({ hasText: 'Due for deletion' })).toContainText('0');

    await page.locator('#retention-days').selectOption('7');
    const note = page.locator('[data-retention-deletion-note]');
    await expect(note).toContainText('Saving this permanently deletes 42 detections older than 7 days at the next cleanup (on restart, then every 24 hours).');
    await expect(note).toContainText('Favourites and the newest 3 detections of each species are kept.');
    await expect(page.locator('#retention-days')).toHaveAttribute('aria-describedby', 'retention-deletion-note');
    // The tiles still describe the saved policy.
    await expect(tiles.filter({ hasText: 'Retention' })).toContainText('30');
    await page.screenshot({ path: testInfo.outputPath('retention-shrink-note.png'), fullPage: true });

    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    const dialog = page.getByRole('alertdialog').or(page.getByRole('dialog'));
    await expect(dialog).toContainText('Delete older history?');
    await expect(dialog.getByRole('button', { name: 'Save and delete 42 detections' })).toBeVisible();
    await page.screenshot({ path: testInfo.outputPath('retention-confirm.png') });
    await dialog.getByRole('button', { name: 'Cancel' }).click();
    await expect(dialog).toHaveCount(0);
    await page.waitForTimeout(300);
    expect(fixture.saves).toEqual([]);

    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await dialog.getByRole('button', { name: 'Save and delete 42 detections' }).click();
    await expect.poll(() => fixture.saves.length).toBe(1);
    expect(fixture.saves[0].retention_days).toBe(7);
    await expect(note).toHaveCount(0);
});

test('a longer window asks nothing and shows no deletion note', async ({ page }) => {
    const fixture = await openDataSettings(page, 30);
    await page.locator('#retention-days').selectOption('90');
    await expect(page.locator('[data-retention-deletion-note]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => fixture.saves.length).toBe(1);
    expect(fixture.previews).toEqual([]);
});

test('Purge Old Records says why it is unavailable while history is kept forever', async ({ page }) => {
    await openDataSettings(page, 0);
    const purge = page.getByRole('button', { name: 'Purge Old Records' });
    await expect(purge).toBeDisabled();
    await expect(purge).toHaveAccessibleDescription('Nothing to purge: history is kept forever.');

    await page.locator('#retention-days').selectOption('365');
    await expect(page.locator('[data-retention-deletion-note]')).toContainText('Saving this permanently deletes 1 detection older than 365 days');
});

test('with automatic cleanup off, saving is not presented as a deletion', async ({ page }) => {
    const fixture = await openDataSettings(page, 30, false);
    await page.locator('#retention-days').selectOption('7');
    await expect(page.locator('[data-retention-deletion-note]')).toContainText('Automatic cleanup is off, so saving deletes nothing by itself.');
    await page.getByRole('button', { name: 'Apply Settings', exact: true }).click();
    await expect.poll(() => fixture.saves.length).toBe(1);
});

test('the Danger Zone puts each consequence beside its own button', async ({ page }, testInfo) => {
    await openDataSettings(page, 30);
    await page.getByRole('button', { name: /Danger Zone/ }).click();
    await expect(page.getByRole('button', { name: 'Clear Personalization Data' })).toHaveAccessibleDescription(/does not delete detections or media/);
    await expect(page.getByRole('button', { name: 'Delete All Favorites' })).toHaveAccessibleDescription(/Removes every favourite marker/);
    await expect(page.getByRole('button', { name: 'Reset Database & Cache' })).toHaveAccessibleDescription(/permanently delete ALL detections/);
    await page.locator('[data-danger-actions]').screenshot({ path: testInfo.outputPath('danger-zone.png') });
});
