import { test, expect } from '@playwright/test';

// A range check flags Red Junglefowl because the bird model names chickens that way. The card says
// so in words and lets the owner keep chickens: declared, and the records moved to Garden.

test.beforeEach(async ({ page }) => {
    await page.route('https://fonts.googleapis.com/**', (route) => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', (route) => route.abort());
});

test('an owner keeps chickens from the range check, and the result is stated', async ({ page }) => {
    const requests: string[] = [];
    await page.route('**/api/garden/domestic-birds/*/keep', async (route) => {
        requests.push(new URL(route.request().url()).pathname);
        await route.fulfill({ json: { bird: 'chicken', declared: true, moved: 8, skipped: 1, remaining: 0 } });
    });
    await page.goto('/browser-tests/species-kept-bird.html');
    const note = page.locator('[data-spotlight-kept-bird="chicken"]');
    await expect(note).toContainText('Red Junglefowl may be a domestic bird: Chickens.');
    await expect(note).toContainText('hidden from bird history, not deleted');
    await note.getByRole('button', { name: 'I keep Chickens: move to Garden' }).click();
    await expect(page.getByText('Moved 8 bird records to Garden. Chickens are now in Domestic birds you keep.')).toBeVisible();
    await expect(page.getByText('1 record could not move and stays in bird history.')).toBeVisible();
    await expect(page.locator('[data-kept-changes]')).toHaveText('1');
    expect(requests).toEqual(['/api/garden/domestic-birds/chicken/keep']);
});

test('a failed move says so and changes nothing', async ({ page }) => {
    await page.route('**/api/garden/domestic-birds/*/keep', (route) => route.fulfill({ status: 409, json: { detail: 'Turn on Garden animals before moving a record to Garden' } }));
    await page.goto('/browser-tests/species-kept-bird.html');
    const button = page.getByRole('button', { name: 'I keep Chickens: move to Garden' });
    await button.click();
    await expect(page.getByText('Turn on Garden animals before moving a record to Garden')).toBeVisible();
    await expect(page.locator('[data-kept-changes]')).toHaveText('0');
    await expect(button).toBeEnabled();
});

test('a visitor sees no kept-bird action', async ({ page }) => {
    await page.goto('/browser-tests/species-kept-bird.html?viewer=guest');
    await expect(page.locator('[data-spotlight-checks]')).toBeVisible();
    await expect(page.locator('[data-spotlight-kept-bird]')).toHaveCount(0);
});
