import { test, expect, type Page } from '@playwright/test';
import { openSettings } from './settings-page-mock';

// "Delete all history" states how many detections it removes. The figure is read when the owner
// asks, on a tab that never loaded it; the question cannot be confirmed before the read lands and
// never falls back to a number nobody measured.
test.use({ viewport: { width: 1440, height: 900 } });

interface StatsFixture {
    requests: number;
    resets: number;
    release: () => void;
}

async function openDangerZone(page: Page, answer: { status: number; json: unknown }): Promise<StatsFixture> {
    let release = (): void => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    const fixture: StatsFixture = { requests: 0, resets: 0, release };
    await openSettings(page);
    await page.route(url => url.pathname === '/api/maintenance/stats', async route => {
        fixture.requests += 1;
        await held;
        await route.fulfill(answer);
    });
    await page.route(url => url.pathname === '/api/backfill/reset', async route => {
        fixture.resets += 1;
        await route.fulfill({ json: { status: 'completed', message: 'Deleted 931 detections.', deleted_count: 931, cache_stats: {} } });
    });
    await page.getByRole('link', { name: 'Maintenance', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Delete data', exact: true })).toBeVisible();
    return fixture;
}

const stats = (total: unknown) => ({
    status: 200,
    json: {
        total_detections: total, oldest_detection: '2026-10-18T07:08:46', retention_days: 0, detections_to_cleanup: 0,
        kept_newest_per_species: 0, automatic_cleanup: true, preview_retention_days: null, preview_detections_to_cleanup: null
    }
});

test('the question counts the detections first and cannot be confirmed until it has', async ({ page }, testInfo) => {
    const fixture = await openDangerZone(page, stats(931));
    // Maintenance never reads the storage figures on its own.
    expect(fixture.requests).toBe(0);

    await page.getByRole('button', { name: 'Delete all history', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    const confirm = dialog.getByRole('button', { name: 'Delete all history permanently', exact: true });
    await expect(dialog).toContainText('Counting the detections this would delete…');
    await expect(dialog).not.toContainText(/\d/);
    await expect(confirm).toBeDisabled();
    await page.screenshot({ path: testInfo.outputPath('delete-all-counting.png') });

    fixture.release();
    await expect(dialog).toContainText('Delete all 931 detections, every cached photo and clip, and every archived favourite? This cannot be undone.');
    await expect(confirm).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath('delete-all-counted.png') });
    expect(fixture.resets).toBe(0);

    await confirm.click();
    await expect.poll(() => fixture.resets).toBe(1);
});

test('a count that cannot be read is left out, and the question still says it cannot be undone', async ({ page }, testInfo) => {
    const fixture = await openDangerZone(page, { status: 503, json: { detail: 'database is locked' } });
    fixture.release();
    await page.getByRole('button', { name: 'Delete all history', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Delete all detections, every cached photo and clip, and every archived favourite? The number of detections could not be read. This cannot be undone.');
    await expect(dialog).not.toContainText(/\d/);
    await expect(dialog.getByRole('button', { name: 'Delete all history permanently', exact: true })).toBeEnabled();
    await page.screenshot({ path: testInfo.outputPath('delete-all-uncounted.png') });

    await dialog.getByRole('button', { name: 'Cancel', exact: true }).click();
    await expect(dialog).toHaveCount(0);
    expect(fixture.resets).toBe(0);
});

test('an answer without a whole number is not read as zero', async ({ page }) => {
    const fixture = await openDangerZone(page, stats(null));
    fixture.release();
    await page.getByRole('button', { name: 'Delete all history', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('The number of detections could not be read.');
    await expect(dialog).not.toContainText(/\d/);
});

test('cancelling while it counts deletes nothing, even after the count arrives', async ({ page }) => {
    const fixture = await openDangerZone(page, stats(931));
    await page.getByRole('button', { name: 'Delete all history', exact: true }).click();
    const dialog = page.getByRole('alertdialog');
    await expect(dialog).toContainText('Counting the detections this would delete…');
    // Focus lands on the safe answer; Escape is answered by the dialog that holds it.
    await expect(dialog.getByRole('button', { name: 'Cancel', exact: true })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(dialog).toHaveCount(0);
    fixture.release();
    await page.waitForTimeout(300);
    await expect(dialog).toHaveCount(0);
    expect(fixture.resets).toBe(0);
});
