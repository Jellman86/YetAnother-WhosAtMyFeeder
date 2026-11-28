import { expect, test } from '@playwright/test';
import { openRecordLayout } from './record-layout-fixture';

/**
 * A record whose snapshot and video readings named different birds (#804) shows both readings in
 * its evidence, says in words that a person should look, and drops the notice and the plain video
 * card that would otherwise say the same thing twice.
 */
const readings = '[data-record-readings]';

test('a kept snapshot name shows both readings, asks for a look and offers to score again', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { readings: 'kept', lineage: false });
    const panel = page.locator(readings);
    await expect(panel).toHaveAttribute('data-record-readings', 'needs-person');
    await expect(panel.locator('[data-status-chip="attention"]')).toHaveText('Readings disagree');
    await expect(panel.locator('[data-record-reading="snapshot"]')).toContainText('Common Wood-Pigeon');
    await expect(panel.locator('[data-record-reading="snapshot"]')).toContainText('99%');
    await expect(panel.locator('[data-record-reading="video"]')).toContainText('Pica pica');
    await expect(panel.locator('[data-record-reading="video"]')).toContainText('67%');
    await expect(panel.locator('[data-record-readings-score-again]')).toBeVisible();
    await expect(page.getByText('Video found a match: confirm to apply')).toHaveCount(0);
});

test('a name taken from the video still shows the snapshot that disagreed, without a second action', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { readings: 'renamed' });
    const panel = page.locator(readings);
    await expect(panel).toHaveAttribute('data-record-readings', 'needs-person');
    await expect(panel.locator('[data-record-reading="snapshot"]')).toContainText('Carrion Crow');
    await expect(panel.locator('[data-record-reading="video"]')).toContainText('Eurasian Magpie');
    await expect(panel.locator('[data-record-readings-score-again]')).toHaveCount(0);
});

test('once the owner has named the bird the readings stay, without amber', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { readings: 'decided' });
    const panel = page.locator(readings);
    await expect(panel).toHaveAttribute('data-record-readings', 'decided');
    await expect(panel.locator('[data-status-chip]')).toHaveCount(0);
    await expect(panel).toContainText('You chose the name shown.');
});

test('a guest sees no readings comparison', async ({ page }) => {
    await openRecordLayout(page, { width: 1440, height: 900 }, { readings: 'kept', guest: true, lineage: false });
    await expect(page.locator(readings)).toHaveCount(0);
});

test('the readings fit a phone without sideways scrolling', async ({ page }) => {
    await openRecordLayout(page, { width: 390, height: 844 }, { readings: 'kept', lineage: false });
    await page.locator(readings).scrollIntoViewIfNeeded();
    await expect(page.locator(readings)).toBeVisible();
    expect(await page.evaluate(() => document.documentElement.scrollWidth - innerWidth)).toBeLessThanOrEqual(0);
    const panel = await page.locator(readings).boundingBox();
    expect(panel && panel.x >= 0 && panel.x + panel.width <= 390).toBe(true);
});
