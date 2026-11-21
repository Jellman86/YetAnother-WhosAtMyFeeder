import { test, expect } from '@playwright/test';

test('cache limits and scanning use the existing settings controls without overflow', async ({ page }, testInfo) => {
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/media-settings.html');
    // No limit is a switch that is off, never a 0 to type: the size field appears with the switch.
    await expect(page.getByRole('spinbutton', { name: /^Storage limit in GB/ })).toHaveCount(0);
    await page.getByRole('switch', { name: /^Limit the space photos and video use/ }).click();
    const limit = page.getByRole('spinbutton', { name: /^Storage limit in GB/ });
    await limit.fill('2');
    await limit.blur();
    // The interacting per-species limits wait under advanced options, each behind its own switch.
    await page.getByRole('button', { name: /^Show advanced options.*Per-species limits/ }).click();
    await page.getByRole('switch', { name: /^Limit visits per species with photos and video/ }).click();
    await page.getByRole('spinbutton', { name: /^Visits per species with photos and video/ }).fill('50');
    await page.getByRole('button', { name: /^Show advanced options.*Snapshot quality/ }).click();
    await page.getByRole('combobox', { name: 'Bird scanning effort', exact: true }).selectOption('standard');
    await expect(page.getByRole('status', { name: 'Selected cache settings' })).toHaveText('50 / 2048 / standard');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    const card = page.locator('section').filter({ has: page.getByRole('heading', { name: 'Photos and video', exact: true }) });
    // Photographs and visit media are always kept (#622): no switch turns them off.
    await expect(card.locator('[data-media-always-kept]')).toBeVisible();
    await expect(card.getByRole('switch', { name: /^Snapshots/ })).toHaveCount(0);
    await expect(card.getByRole('switch', { name: /^Media Cache/ })).toHaveCount(0);
    await expect(card.getByRole('switch', { name: /^Keep copies of Frigate's event clips/ })).toHaveCount(1);
    await expect(card.locator('[data-media-storage-unavailable]')).toHaveCount(0);
    const bounds = await card.boundingBox();
    expect(bounds?.width ?? 0).toBeGreaterThan(300);
    await card.screenshot({ path: testInfo.outputPath('media-settings.png') });
    await page.evaluate(() => document.documentElement.classList.add('theme-bluetit', 'dark'));
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
    // The blue tit dark panel and ground tokens from app.css; the section's rows sit on its card.
    await expect(card.locator('[data-settings-section-body]')).toHaveCSS('background-color', 'rgb(11, 19, 34)');
    await expect(page.locator('body')).toHaveCSS('background-color', 'rgb(5, 10, 20)');
    await card.screenshot({ path: testInfo.outputPath('media-settings-dark.png'), animations: 'disabled' });
});

test('a cleared or out-of-range storage limit keeps the saved limit and says why', async ({ page }) => {
    await page.goto('/browser-tests/media-settings.html');
    await page.getByRole('switch', { name: /^Limit the space photos and video use/ }).click();
    const limit = page.getByRole('spinbutton', { name: /^Storage limit in GB/ });
    const chosen = page.getByRole('status', { name: 'Selected cache settings' });
    await limit.fill('2');
    await limit.blur();
    await expect(chosen).toHaveText('0 / 2048 / intensive');
    // Clearing the field must never stand in for a tiny limit that evicts most of the media.
    for (const typed of ['', '0', '2000']) {
        await limit.fill(typed);
        await limit.blur();
        await expect(chosen).toHaveText('0 / 2048 / intensive');
        await expect(limit).toHaveAttribute('aria-invalid', 'true');
        await expect(limit).toHaveAccessibleDescription(/Enter a size from 0\.5 to 1024 GB\. The limit stays at 2 GB until you do\./);
        await expect(page.getByRole('status', { name: 'Storage limit invalid' })).toHaveText('true');
    }
    await limit.fill('3');
    await limit.blur();
    await expect(chosen).toHaveText('0 / 3072 / intensive');
    await expect(limit).not.toHaveAttribute('aria-invalid', 'true');
    await expect(page.getByRole('status', { name: 'Storage limit invalid' })).toHaveText('false');
});

test('the storage summary names every rule that removes media, the per-species cap included', async ({ page }) => {
    await page.goto('/browser-tests/media-settings.html');
    const summary = page.locator('[data-settings-row]').filter({ has: page.getByRole('switch', { name: /^Limit the space photos and video use/ }) });
    await expect(summary).toContainText('No size limit: photos and video stay until the history window removes their visits.');
    await page.getByRole('button', { name: /^Show advanced options.*Per-species limits/ }).click();
    await page.getByRole('switch', { name: /^Limit visits per species with photos and video/ }).click();
    // With a cap on, "until the history window" would be a promise the cap breaks.
    await expect(summary).not.toContainText('until the history window');
    await expect(summary).toContainText('No size limit. Each species keeps photos and video only for its newest 100 visits.');
});

test('favourites archive figures wait for a measurement instead of showing zero', async ({ page }) => {
    await page.goto('/browser-tests/media-settings.html');
    const archive = page.locator('[data-archive-usage]');
    await expect(archive).toContainText('Measuring…');
    await expect(archive).not.toContainText('0 kept');
});

test('a media folder that cannot be written is said plainly on the card', async ({ page }) => {
    await page.goto('/browser-tests/media-settings.html?storage=unavailable');
    const notice = page.locator('[data-media-storage-unavailable]');
    await expect(notice).toBeVisible();
    await expect(notice).toHaveText(/can't be written, so photos and video are not being kept/);
});
