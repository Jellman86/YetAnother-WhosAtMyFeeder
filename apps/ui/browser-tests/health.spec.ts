import { test, expect, type Locator } from '@playwright/test';

const thumbnail = '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect width="160" height="90" fill="#147d64"/></svg>';

test.beforeEach(async ({ page }) => {
    // Fixtures never contact a real backend or send a notification. Fail unexpected
    // API requests as well as JavaScript exceptions, rather than letting mocks hide them.
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        if (/\/frigate\/browser-[\w-]+\/thumbnail\.jpg/.test(route.request().url())) {
            await route.fulfill({ contentType: 'image/svg+xml', body: thumbnail });
        } else {
            throw new Error(`Unexpected fixture API request: ${route.request().method()} ${route.request().url()}`);
        }
    });
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/fixture.html');
    await expect(page.locator('[data-health-activity-row]')).toHaveCount(3);
});

async function expectPortalledAndUnclipped(panel: Locator): Promise<void> {
    await expect(panel).toBeVisible();
    await expect.poll(() => panel.evaluate(node => {
        const rect = node.getBoundingClientRect();
        const outsideCard = !node.closest('[data-health-activity-timeline]');
        const visible = document.elementFromPoint(rect.left + rect.width / 2, rect.bottom - 3);
        return outsideCard && node.contains(visible) && rect.left >= 0 && rect.right <= innerWidth
            && rect.top >= 0 && rect.bottom <= innerHeight;
    })).toBe(true);
}

test('recorded, filtered and failed rows stay distinct and only records can open', async ({ page }) => {
    await expect(page.locator('[data-health-activity-row]').first()).toHaveAttribute('data-row-kind', 'filtered');
    await expect(page.locator('[data-row-kind="filtered"]')).toContainText('20%');
    await expect(page.locator('[data-row-kind="fault"]')).toContainText('Pipeline fault');
    await expect(page.locator('[data-row-kind="filtered"]')).not.toContainText('Pipeline fault');
    await expect(page.getByRole('button', { name: /View record:/ })).toHaveCount(1);
    await page.getByRole('button', { name: /View record:/ }).click();
    await expect(page.getByLabel('Selected record')).toHaveText('browser-recorded');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
});

test('filtered preview escapes clipping, supports keyboard and cleans up on unmount', async ({ page }) => {
    const trigger = page.locator('[data-row-kind="filtered"] button');
    await trigger.focus();
    await trigger.press('Enter');
    const panel = page.locator('[data-filtered-frame-preview-panel]');
    await expectPortalledAndUnclipped(panel);
    await trigger.press('Escape');
    await expect(panel).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await trigger.press('Enter');
    await expect(panel).toBeVisible();
    // Do not move focus: otherwise blur could hide the portal before unmount,
    // masking a leaked portalled node in the component's teardown.
    await page.getByRole('button', { name: 'Toggle mount' }).evaluate(button => (button as HTMLButtonElement).click());
    await expect(panel).toHaveCount(0);
});

test('recorded preview escapes clipping and opens the selected record', async ({ page, isMobile }) => {
    const trigger = page.locator('[data-detection-preview] button').first();
    if (isMobile) await trigger.tap();
    else await trigger.hover();
    if (isMobile) {
        await expect(page.getByLabel('Selected record')).toHaveText('browser-recorded');
    } else {
        await expectPortalledAndUnclipped(page.locator('[data-detection-preview-panel]'));
        await trigger.click();
        await expect(page.getByLabel('Selected record')).toHaveText('browser-recorded');
    }
});

test('expired thumbnail has an honest stable placeholder', async ({ page }) => {
    await page.route('**/api/frigate/browser-filtered/thumbnail.jpg*', route => route.fulfill({ status: 404 }));
    await page.reload();
    const trigger = page.locator('[data-row-kind="filtered"] button');
    await expect(trigger.locator('img')).toHaveCount(0);
    await trigger.click();
    const panel = page.locator('[data-filtered-frame-preview-panel]');
    await expect(panel).toContainText('Frigate no longer has this frame');
    await expectPortalledAndUnclipped(panel);
});

test('loading and empty states do not present stale detections', async ({ page }) => {
    await page.getByLabel('Fixture state').selectOption('loading');
    await expect(page.locator('[data-health-activity-loading]')).toBeVisible();
    await expect(page.locator('[data-health-activity-row]')).toHaveCount(0);
    await page.getByLabel('Fixture state').selectOption('empty');
    await expect(page.getByText('No activity since startup')).toBeVisible();
    await expect(page.locator('[data-health-activity-loading]')).toHaveCount(0);
    await page.getByLabel('Fixture state').selectOption('events');
    await expect(page.locator('[data-health-activity-row]')).toHaveCount(3);
});
