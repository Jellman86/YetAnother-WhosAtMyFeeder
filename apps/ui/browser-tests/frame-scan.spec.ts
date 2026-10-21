import { test, expect, type Page } from '@playwright/test';

// Set UI_SHOTS to a directory to keep review screenshots of each ribbon size.
const environment = (globalThis as { process?: { env: Record<string, string | undefined> } }).process?.env ?? {};

async function open(page: Page): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.goto('/browser-tests/frame-scan.html');
    await expect(page.locator('[data-fixture="overlay"] [role="progressbar"]')).toBeVisible();
}

test('every frame keeps its place and the ribbon never resizes as results arrive', async ({ page }) => {
    await open(page);
    const overlay = page.locator('[data-fixture="overlay"]');
    const before = await overlay.boundingBox();
    await expect(overlay.locator('[data-frame-scan-tone]')).toHaveCount(12);
    await expect(overlay.locator('[data-frame-scan-tone="pending"]')).toHaveCount(12);
    await expect(overlay.getByText('Waiting for the first frame')).toBeVisible();

    await page.getByRole('button', { name: 'Read four frames' }).click();
    await expect(overlay.locator('[data-frame-scan-tone="pending"]')).toHaveCount(8);
    await expect(overlay.locator('[data-frame-scan-tone="strong"]')).toHaveCount(2);
    await expect(overlay.getByText('Clearest so far: frame 3, Eurasian Blue Tit 91%')).toBeVisible();
    expect(await overlay.boundingBox()).toEqual(before);
});

test('the progress is announced in words, and colour is backed by a legend and scores', async ({ page }) => {
    await open(page);
    await page.getByRole('button', { name: 'Read four frames' }).click();
    const bar = page.locator('[data-fixture="detail"]').getByRole('progressbar', { name: 'Video frames read' });
    await expect(bar).toHaveAttribute('aria-valuenow', '4');
    await expect(bar).toHaveAttribute('aria-valuemax', '12');
    await expect(bar).toHaveAttribute('aria-valuetext', '4 of 12 frames read');
    const detail = page.locator('[data-fixture="detail"]');
    await expect(detail.getByText('80% and over')).toBeVisible();
    await expect(detail.getByText('Under 50%')).toBeVisible();
    await expect(detail.getByText('88%')).toBeVisible();
});

test('the playhead sits over the frame being read and leaves once the run completes', async ({ page }) => {
    await open(page);
    await page.getByRole('button', { name: 'Read four frames' }).click();
    const overlay = page.locator('[data-fixture="overlay"]');
    const playhead = overlay.locator('.frame-scan-playhead');
    const fifth = overlay.locator('[data-frame-scan-tone]').nth(4);
    await expect(playhead).toBeVisible();
    await expect.poll(async () => {
        const [head, bar] = await Promise.all([playhead.boundingBox(), fifth.boundingBox()]);
        if (!head || !bar) return false;
        const centre = head.x + head.width / 2;
        return centre >= bar.x - 1 && centre <= bar.x + bar.width + 1;
    }).toBe(true);
    for (let step = 0; step < 2; step += 1) await page.getByRole('button', { name: 'Read four frames' }).click();
    await expect(playhead).toHaveCount(0);
    await expect(overlay.getByText('All 12 frames read')).toBeVisible();
});

test('a long clip fits every frame without scrolling the card sideways', async ({ page }) => {
    await open(page);
    await page.getByRole('button', { name: 'Long clip' }).click();
    for (const variant of ['card', 'compact', 'overlay']) {
        const section = page.locator(`[data-fixture="${variant}"]`);
        await expect(section.locator('[data-frame-scan-tone]')).toHaveCount(240);
        const overflow = await section.locator('.frame-scan-ribbon').evaluate(node => node.scrollWidth - node.clientWidth);
        expect(overflow).toBeLessThanOrEqual(0);
    }
});

test('the Explorer card shows the ribbon inside its analysis overlay', async ({ page }) => {
    await open(page);
    await page.getByRole('button', { name: 'Read four frames' }).click();
    const card = page.locator('[data-fixture="card"]');
    await expect(card.locator('[data-frame-scan-variant="card"]')).toBeVisible();
    await expect(card.getByText('Frame 4/12')).toBeVisible();
    const shots = environment.UI_SHOTS;
    if (shots) {
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await page.screenshot({ path: `${shots}/frame-scan-light.png`, fullPage: true });
        await page.emulateMedia({ colorScheme: 'dark' });
        await page.evaluate(() => { document.documentElement.classList.add('dark'); document.documentElement.dataset.theme = 'dark'; });
        await page.screenshot({ path: `${shots}/frame-scan-dark.png`, fullPage: true });
    }
});
