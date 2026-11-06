import { test, expect } from '@playwright/test';

for (const surface of ['record', 'queue']) {
    test(`${surface}: identification input stays honest after an owner choice at phone text size`, async ({ page }, testInfo) => {
        await page.setViewportSize({ width: 320, height: 740 });
        await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
        await page.route('https://fonts.gstatic.com/**', route => route.abort());
        await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: [] }));
        await page.goto(`/browser-tests/review-media.html?surface=${surface}&queue=dunnock`);
        await expect(page.locator('[data-classification-source]').first()).toBeVisible();
        await page.evaluate(() => window.reviewMedia?.updateParent({
            classification_input: { source: 'full_frame', is_cropped: false },
            initial_classification_input: { source: 'full_frame', is_cropped: false }
        }));
        await page.addStyleTag({ content: 'html{font-size:200%!important}' });
        const line = page.locator('[data-classification-source]').first();
        await expect(line).toContainText('whole camera view');
        expect(await line.evaluate(el => el.scrollWidth <= el.clientWidth + 1)).toBe(true);
        await page.evaluate(() => window.reviewMedia?.updateParent({
            manual_tagged: true, classification_input: { source: 'owner_species_choice' }
        }));
        await expect(line).toHaveText('Named by you');
        if (surface === 'record') {
            const original = page.locator('[data-initial-classification-source]');
            await original.locator('summary').click();
            await expect(original.locator('[data-classification-source]')).toContainText('whole camera view');
        }
        await page.screenshot({ path: testInfo.outputPath(`${surface}-source-320-200.png`), fullPage: true });
    });
}
