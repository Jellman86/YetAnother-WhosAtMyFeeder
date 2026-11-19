import { expect, test, type Page } from '@playwright/test';
import { openSaveDetails, openSettings, saveBar, saveButton, saveDetails } from './settings-page-mock';

// #1044: the visit gap is the owner's setting, beside the naming threshold. It saves with the rest
// of the form, a refused value is marked on the field in plain words, and the card says what the
// gap can and cannot do.

const tabLink = (page: Page, name: string) => page.locator('[data-settings-navigation]').getByRole('link', { name, exact: true });
const gapField = (page: Page) => page.getByRole('spinbutton', { name: 'Visit gap' });

async function openIdentification(page: Page, saved: Record<string, unknown> = {}, refuse = false) {
    const harness = await openSettings(page, saved, refuse
        ? {
            refuseWrite: () => ({
                status: 422,
                json: { detail: [{ type: 'less_than_equal', loc: ['body', 'visit_gap_seconds'], msg: 'Input should be less than or equal to 300', ctx: { le: 300 } }] }
            })
        }
        : {});
    await tabLink(page, 'Identifying birds').click();
    await expect(gapField(page)).toBeVisible({ timeout: 15_000 });
    return harness;
}

test('the visit gap shows the saved value and saves a new one with the form', async ({ page }) => {
    const harness = await openIdentification(page, { visit_gap_seconds: 45 });
    await expect(gapField(page)).toHaveValue('45');
    await expect(saveBar(page)).toHaveCount(0);

    await gapField(page).fill('12');
    await expect(saveBar(page)).toBeVisible();
    await saveButton(page).click();
    await expect.poll(() => harness.writes.length).toBe(1);
    expect(harness.writes[0].visit_gap_seconds).toBe(12);
    await expect(saveBar(page)).toHaveCount(0);
});

test('an install that never chose a gap shows the default minute', async ({ page }) => {
    await openIdentification(page);
    await expect(gapField(page)).toHaveValue('60');
});

test('a gap the server refuses is marked on the field with what to enter', async ({ page }) => {
    await openIdentification(page, {}, true);
    await gapField(page).fill('900');
    await saveButton(page).click();
    await expect(gapField(page)).toHaveAttribute('aria-invalid', 'true');
    await expect(page.locator('[data-field-error="visit_gap_seconds"]')).toHaveText('Enter 300 or less.');
    // The save details name the refused field, rather than calling it another setting.
    await openSaveDetails(page);
    await expect(saveDetails(page)).toContainText('Visit gap');
    await expect(saveDetails(page)).not.toContainText('Another setting');
});

test('the card says what the gap does, what it cannot count, and what happens to history', async ({ page }) => {
    await openIdentification(page);
    const card = page.locator('[data-visit-gap-notes]');
    await expect(page.getByRole('heading', { name: 'Counting visits' })).toBeVisible();
    await expect(page.getByText('Captures of one species on one camera no more than the visit gap apart count as one visit.', { exact: false })).toBeVisible();
    await expect(card).toContainText('cannot count individual birds');
    await expect(card).toContainText('keep the visit counts they were saved with');
    // The range and unit are read with the field, not left to the placeholder.
    await expect(gapField(page)).toHaveAccessibleDescription(/From 5 to 300 seconds\. The default is 60\. seconds/);
});
