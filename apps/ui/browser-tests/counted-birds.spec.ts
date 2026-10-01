import { test, expect } from '@playwright/test';

const frame = '<svg xmlns="http://www.w3.org/2000/svg" width="320" height="180"><rect width="320" height="180" fill="#334155"/><circle cx="67" cy="62" r="16" fill="#a7f3d0"/><circle cx="220" cy="77" r="16" fill="#fca5a5"/></svg>';

test.beforeEach(async ({ page }) => {
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const path = new URL(route.request().url()).pathname;
        if (path === '/api/fixture/whole.svg') {
            await route.fulfill({ contentType: 'image/svg+xml', body: frame });
        } else if (path === '/api/frigate/fixture-event/birds/2' && route.request().method() === 'PATCH') {
            const change = route.request().postDataJSON();
            await route.fulfill({ json: {
                id: 2, bird_index: 1, candidate_id: 'crop-two', clip_variant: 'event', frame_index: 1,
                crop_box: [195, 50, 245, 105], detector_confidence: 0.72,
                species: change.species ?? 'Northern Cardinal', classifier_label: null, classifier_score: 0.25,
                manual_species: true, is_hidden: change.is_hidden ?? false
            } });
        } else {
            throw new Error(`Unexpected counted birds fixture API request: ${route.request().method()} ${path}`);
        }
    });
    page.on('pageerror', error => { throw error; });
    await page.goto('/browser-tests/counted-birds.html');
});

test('marks both birds on the whole frame and updates the count when one is excluded', async ({ page }, testInfo) => {
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(2);
    await expect(page.locator('[data-counted-birds]')).toContainText('2');
    const image = await page.locator('[data-counted-birds-frame] img').boundingBox();
    const second = await page.locator('[data-counted-bird-outline]').nth(1).boundingBox();
    expect(image).not.toBeNull();
    expect(second).not.toBeNull();
    expect((second!.x - image!.x) / image!.width).toBeCloseTo(195 / 320, 1);

    await page.getByRole('button', { name: 'Correct' }).nth(1).click();
    await page.getByRole('textbox', { name: 'Species for bird 2' }).fill('Northern');
    await page.getByRole('button', { name: 'Northern Cardinal' }).click();
    await page.getByRole('button', { name: 'Save' }).click();
    await expect(page.locator('[data-counted-bird-list]')).toContainText('Northern Cardinal');

    await page.getByRole('button', { name: 'Exclude' }).nth(1).click();
    await expect(page.locator('[data-counted-bird-outline]')).toHaveCount(1);
    await expect(page.locator('[data-counted-birds] [aria-label]')).toHaveAttribute('aria-label', 'Birds counted: 1');
    await page.screenshot({ path: testInfo.outputPath('counted-birds.png'), fullPage: true });
});


test('bird correction targets remain usable at 320px without overlapping', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 800 });
    const controls = page.locator('[data-counted-birds] button');
    async function checkTargets(): Promise<void> {
        const bounds = await controls.evaluateAll(nodes => nodes.map(node => ({ ...node.getBoundingClientRect().toJSON(), label: node.textContent })));
        for (const target of bounds) {
            expect(target.width, `${target.label} width`).toBeGreaterThanOrEqual(44);
            expect(target.height, `${target.label} height`).toBeGreaterThanOrEqual(44);
        }
        for (let a = 0; a < bounds.length; a += 1) for (let b = a + 1; b < bounds.length; b += 1) {
            expect(Math.min(bounds[a].right, bounds[b].right) - Math.max(bounds[a].left, bounds[b].left) > .5
                && Math.min(bounds[a].bottom, bounds[b].bottom) - Math.max(bounds[a].top, bounds[b].top) > .5).toBe(false);
        }
    }
    await checkTargets();
    await page.getByRole('button', { name: 'Correct' }).nth(1).focus();
    await page.keyboard.press('Enter');
    await page.getByRole('textbox', { name: 'Species for bird 2' }).fill('Northern');
    await expect(page.getByRole('button', { name: 'Northern Cardinal' })).toBeVisible();
    await checkTargets();
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('bird-targets-320.png'), fullPage: true });
});
