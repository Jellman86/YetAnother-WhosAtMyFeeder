import { test, expect, type Page } from '@playwright/test';

// The record says "Frigate no longer has this event" only on a not-found answer. A Frigate that
// could not be asked gets its own cause and next step, and no "error details" when no error exists.
test.use({ viewport: { width: 1440, height: 900 } });

async function openRecord(page: Page, availability: Record<string, unknown>): Promise<void> {
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ json: [] }));
    await page.goto('/browser-tests/review-media.html?surface=record&queue=dunnock');
    await page.waitForFunction(() => Boolean(window.reviewMedia));
    await expect(page.getByRole('dialog').first()).toBeVisible();
    await page.evaluate(identity => window.reviewMedia?.updateParent(identity), availability);
}

const notice = (page: Page) => page.getByRole('dialog').first().getByRole('status').filter({ hasText: /Frigate/ });

const unanswered = [
    ['unreachable', 'YA-WAMF could not reach Frigate, so it is not known whether Frigate still has this event. Check that Frigate is running, then reopen this record.'],
    ['timed_out', 'Frigate did not answer in time, so it is not known whether it still has this event. Reopen this record in a moment. If it keeps happening, check how busy Frigate is.'],
    ['failed', "Frigate answered with an error, so it is not known whether it still has this event. Check Frigate's log, then reopen this record."],
    ['not_checked', 'Frigate has not been asked about this event yet. Reopen this record to check.']
] as const;

for (const [check, sentence] of unanswered) {
    test(`a check that ${check} states its cause and next step, never an absence`, async ({ page }, testInfo) => {
        await openRecord(page, { has_frigate_event: false, frigate_event_check: check });
        await expect(notice(page)).toContainText(sentence);
        await expect(page.getByRole('dialog').first()).not.toContainText('no longer has');
        // Nothing failed, so there are no error details to open.
        await expect(notice(page).locator('details')).toHaveCount(0);
        await notice(page).scrollIntoViewIfNeeded();
        await page.screenshot({ path: testInfo.outputPath(`record-frigate-${check}.png`) });
    });
}

test('a not-found answer is the one that says Frigate no longer has the event', async ({ page }, testInfo) => {
    await openRecord(page, { has_frigate_event: false, frigate_event_check: 'not_found' });
    await expect(notice(page)).toContainText('Frigate no longer has this event or media.');
    await notice(page).scrollIntoViewIfNeeded();
    await page.screenshot({ path: testInfo.outputPath('record-frigate-not_found.png') });
});

test('an event Frigate still has shows no Frigate notice', async ({ page }) => {
    await openRecord(page, { has_frigate_event: true, frigate_event_check: 'found' });
    await expect(notice(page)).toHaveCount(0);
});
