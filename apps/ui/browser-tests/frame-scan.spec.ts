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

test('an Explorer list row draws the scan behind itself without growing or moving', async ({ page }) => {
    await open(page);
    const list = page.locator('[data-fixture="row"]');
    const rows = list.locator('[data-detection-row]');
    const scanning = rows.nth(1);
    const quietHeight = (await rows.nth(0).boundingBox())?.height;
    const before = await scanning.boundingBox();

    await page.getByRole('button', { name: 'Read four frames' }).click();
    const backdrop = scanning.locator('[data-frame-scan-variant="backdrop"]');
    await expect(backdrop).toHaveAttribute('aria-hidden', 'true');
    await expect(backdrop.locator('[data-frame-scan-tone]')).toHaveCount(12);
    await expect(backdrop.locator('[data-frame-scan-tone="pending"]')).toHaveCount(8);
    await expect(scanning.getByText('Scanning video frames')).toBeVisible();
    const count = scanning.getByRole('progressbar', { name: 'Video frames read' });
    await expect(count).toHaveAttribute('aria-valuetext', '4 of 12 frames read');
    await expect(count).toContainText('4/12');

    expect(await scanning.boundingBox()).toEqual(before);
    expect(before?.height).toBe(quietHeight);
    await expect(rows.nth(0).locator('[data-frame-scan-variant]')).toHaveCount(0);
    await expect(scanning.getByRole('button', { name: /^Open Great Tit/ })).toBeVisible();

    const shots = environment.UI_SHOTS;
    if (shots) {
        await page.emulateMedia({ reducedMotion: 'reduce' });
        await list.screenshot({ path: `${shots}/frame-scan-row-light.png` });
        await page.emulateMedia({ colorScheme: 'dark' });
        await page.evaluate(() => { document.documentElement.classList.add('dark'); document.documentElement.dataset.theme = 'dark'; });
        await list.screenshot({ path: `${shots}/frame-scan-row-dark.png` });
    }

    for (let step = 0; step < 2; step += 1) await page.getByRole('button', { name: 'Read four frames' }).click();
    await expect(backdrop.locator('.frame-scan-playhead')).toHaveCount(0);
});

test('while a card is analysed, its readings and play leave the keyboard and the pointer', async ({ page }) => {
    await open(page);
    const analysing = page.locator('[data-fixture="card-analysing"]');
    const idle = page.locator('[data-fixture="card-idle"]');
    // The idle card offers its time, score and play, each reachable by Tab.
    const idleReadings = idle.locator('[data-detection-card-readings]');
    await expect(idleReadings.getByRole('button', { name: /Play/ })).toBeVisible();
    await expect(idleReadings).not.toHaveAttribute('inert', '');

    // Under the opaque analysis overlay they are inert: nothing hidden takes focus or a click.
    const readings = analysing.locator('[data-detection-card-readings]');
    await expect(readings).toHaveAttribute('inert', '');
    await expect(readings).toBeHidden();

    // The card's own record button comes first in it.
    const record = analysing.locator('button').first();
    await record.focus();
    const reached: string[] = [];
    for (let step = 0; step < 4; step += 1) {
        await page.keyboard.press('Tab');
        reached.push(await page.evaluate(() => {
            const active = document.activeElement as HTMLElement | null;
            const card = active?.closest('[data-fixture]')?.getAttribute('data-fixture') ?? 'outside';
            return `${card}:${active?.getAttribute('aria-label') ?? active?.textContent?.trim() ?? ''}`;
        }));
    }
    // Tab leaves the analysed card at once and goes on to the idle card's own controls.
    expect(reached.filter((stop) => stop.startsWith('card-analysing'))).toEqual([]);
    expect(reached.some((stop) => stop.startsWith('card-idle'))).toBe(true);
    await expect(page.locator('[data-fixture-played]')).toHaveAttribute('data-fixture-played', 'none');
});

test('an analysed card keeps its height, wrapping marks and all, and lands at the same height when the analysis ends', async ({ page }) => {
    await open(page);
    const card = page.locator('[data-fixture="card-marked"] [data-detection-card]');
    const readings = page.locator('[data-fixture="card-marked"] [data-detection-card-readings]');
    // At 240px the time, score, play and three marks wrap onto two lines.
    await expect(readings).toHaveAttribute('inert', '');
    const marks = readings.locator('[data-explorer-owner-confirmed], [aria-label], button');
    expect(await marks.count()).toBeGreaterThan(3);
    const during = await card.boundingBox();

    await page.getByRole('button', { name: 'End the analysis' }).click();
    await expect(readings).not.toHaveAttribute('inert', '');
    await expect(readings).toBeVisible();
    const after = await card.boundingBox();
    const lines = await readings.evaluate((node) => Math.round(node.getBoundingClientRect().height));
    expect(lines, 'the readings wrap, which is the case that used to shift').toBeGreaterThan(48);
    expect(after?.height).toBe(during?.height);
});

test('thirty analysed cards are spoken as one start and one finish through the page announcer, and never again', async ({ page }) => {
    await open(page);
    // Every text the shared live region is given, in order.
    await page.evaluate(() => {
        const said: string[] = [];
        (window as unknown as { said: string[] }).said = said;
        const region = document.querySelector('[aria-live]');
        if (!region) throw new Error('no announcer');
        new MutationObserver(() => {
            const text = region.textContent?.trim() ?? '';
            if (text) said.push(text);
        }).observe(region, { childList: true, subtree: true, characterData: true });
    });
    // The raw sequence, every line in the order it was given, so a repeated announcement fails.
    const said = () => page.evaluate(() => [...(window as unknown as { said: string[] }).said]);
    // The fixture's own scanning card is analysing at load: end it, let its lines pass, and start clean.
    await page.getByRole('button', { name: 'End the analysis' }).click();
    await page.waitForTimeout(800);
    await page.evaluate(() => { (window as unknown as { said: string[] }).said.length = 0; });
    // Cards hold no live region of their own.
    await expect(page.locator('[data-fixture="bulk-cards"] [role="status"], [data-fixture="bulk-cards"] [aria-live]')).toHaveCount(0);
    await expect(page.locator('[aria-live]')).toHaveCount(1);

    await page.getByRole('button', { name: 'Analyse thirty' }).click();
    await expect.poll(said).toEqual(['Analysing 30 visits']);
    await page.getByRole('button', { name: 'Finish thirty' }).click();
    await expect.poll(said).toEqual(['Analysing 30 visits', 'Analysis finished for 30 visits']);
    // A second completion of the same runs (as a species correction sends) says nothing more.
    await page.getByRole('button', { name: 'Finish thirty' }).click();
    await page.waitForTimeout(800);
    expect(await said()).toEqual(['Analysing 30 visits', 'Analysis finished for 30 visits']);
});
