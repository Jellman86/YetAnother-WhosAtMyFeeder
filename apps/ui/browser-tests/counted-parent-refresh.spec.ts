import { test, expect, type Page } from '@playwright/test';

const bird = { id: 694, bird_index: 0, candidate_id: 'crop', clip_variant: 'frigate_snapshot', frame_index: 0,
    crop_box: [873, 341, 1112, 480], detector_confidence: .509, species: 'Prunella modularis',
    common_name: 'Dunnock', scientific_name: 'Prunella modularis', classifier_label: 'Prunella modularis',
    classifier_score: .4519, identity_source: 'visit', identity_score: .9396 as number | null, manual_species: false, is_hidden: false };

function candidates(version: string) {
    return [
        { candidate_id: `${version}-full`, frame_index: 0, clip_variant: 'frigate_snapshot', source_mode: 'full_frame',
            image_url: `/api/${version}-full.jpg`, thumbnail_url: `/api/${version}-full.jpg`, crop_box: null, ranking_score: .8 },
        { candidate_id: `${version}-crop`, frame_index: 0, clip_variant: 'frigate_snapshot', source_mode: 'model_crop',
            image_url: `/api/${version}-crop.jpg`, thumbnail_url: `/api/${version}-crop.jpg`, crop_box: bird.crop_box,
            ranking_score: .8, selected: true }
    ];
}

async function open(page: Page, surface: string) {
    let currentBird = { ...bird };
    let version = 'old';
    let lists = 0;
    let statuses = 0;
    let nextHold: Promise<void> | null = null;
    await page.route('https://fonts.googleapis.com/**', route => route.fulfill({ contentType: 'text/css', body: '' }));
    await page.route('https://fonts.gstatic.com/**', route => route.abort());
    await page.route(url => url.pathname.startsWith('/api/'), async route => {
        const url = new URL(route.request().url());
        if (url.pathname.endsWith('/snapshot/candidates')) {
            lists += 1;
            const response = { candidates: candidates(version), birds: [currentBird],
                current_candidate_id: `${version}-crop`, current_source: 'hq_candidate_model_crop' };
            const held = nextHold;
            nextHold = null;
            if (held) await held;
            return route.fulfill({ json: response });
        }
        if (url.pathname.endsWith('/snapshot/status')) { statuses += 1; return route.fulfill({ json: {} }); }
        if (url.pathname.endsWith('.jpg')) return route.fulfill({ contentType: 'image/svg+xml',
            body: '<svg xmlns="http://www.w3.org/2000/svg" width="1280" height="720"><rect width="1280" height="720" fill="#334155"/></svg>' });
        return route.fulfill({ json: [] });
    });
    await page.goto(`/browser-tests/review-media.html?surface=${surface}&queue=dunnock`);
    const heading = page.locator('[data-counted-bird-row="694"] [data-counted-bird-select]');
    await expect(heading).toContainText('Dunnock');
    await expect.poll(() => lists).toBe(1);
    return {
        heading,
        lists: () => lists,
        statuses: () => statuses,
        setBird(update: Partial<typeof bird>) { currentBird = { ...currentBird, ...update }; version = 'new'; },
        holdNext() {
            let release = () => {};
            nextHold = new Promise<void>(resolve => { release = resolve; });
            return release;
        }
    };
}

for (const surface of ['record', 'queue']) {
    test(`${surface}: parent confirmation refreshes counted identity immediately and media after settlement`, async ({ page }) => {
        const fixture = await open(page, surface);
        await expect(fixture.heading).toContainText('94%');
        const chosen = page.locator('[data-frame-strip] button[aria-pressed="true"] img');
        await expect(chosen).toHaveAttribute('src', /old/);
        const initialStatuses = fixture.statuses();
        fixture.setBird({ identity_score: null });
        await page.evaluate(() => window.reviewMedia?.updateParent({ manual_tagged: true }));
        await expect(fixture.heading).not.toContainText('%');
        expect(fixture.lists()).toBe(2);
        expect(fixture.statuses()).toBe(initialStatuses);
        await expect(chosen).toHaveAttribute('src', /old/);

        fixture.setBird({ species: 'Unknown Bird', common_name: '', scientific_name: '', identity_source: 'crop', identity_score: .4519 });
        await page.evaluate(() => window.reviewMedia?.updateParent({
            display_name: 'European Robin', common_name: 'European Robin', scientific_name: 'Erithacus rubecula', category_name: 'Erithacus rubecula'
        }));
        await expect(fixture.heading).toContainText('Unknown bird');
        expect(fixture.lists()).toBe(3);
        await expect(chosen).toHaveAttribute('src', /old/);

        await page.evaluate(() => window.reviewMedia?.completeAnalysis('dunnock'));
        if (surface === 'record') await page.getByRole('button', { name: 'Done', exact: true }).click();
        await expect(chosen).toHaveAttribute('src', /new/);
        await expect.poll(() => fixture.lists()).toBe(4);
    });

    test(`${surface}: a late identity read cannot overwrite the completed run`, async ({ page }) => {
        const fixture = await open(page, surface);
        fixture.setBird({ identity_score: null });
        const release = fixture.holdNext();
        await page.evaluate(() => window.reviewMedia?.updateParent({ manual_tagged: true }));
        await expect.poll(() => fixture.lists()).toBe(2);
        fixture.setBird({ species: 'Erithacus rubecula', common_name: 'European Robin', scientific_name: 'Erithacus rubecula' });
        await page.evaluate(() => window.reviewMedia?.completeAnalysis('dunnock'));
        await expect(fixture.heading).toContainText('European Robin');
        release();
        await page.waitForTimeout(250);
        await expect(fixture.heading).toContainText('European Robin');
        expect(fixture.lists()).toBe(3);
    });

    test(`${surface}: older media completion keeps corrections disabled until the newer identity arrives`, async ({ page }) => {
        const fixture = await open(page, surface);
        await fixture.heading.click();
        const correct = page.locator('[data-counted-bird-row="694"] [data-counted-bird-correct]');
        await expect(correct).toBeEnabled();
        const releaseMedia = fixture.holdNext();
        await page.evaluate(() => window.reviewMedia?.completeAnalysis('dunnock'));
        if (surface === 'record') await page.getByRole('button', { name: 'Done', exact: true }).click();
        await expect.poll(() => fixture.lists()).toBe(2);

        fixture.setBird({ identity_score: null });
        const releaseIdentity = fixture.holdNext();
        await page.evaluate(() => window.reviewMedia?.updateParent({ manual_tagged: true }));
        await expect.poll(() => fixture.lists()).toBe(3);
        await expect(correct).toBeDisabled();
        const mediaResponse = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/snapshot/candidates'));
        releaseMedia();
        await mediaResponse;
        await page.evaluate(() => new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve()))));
        await expect(correct).toBeDisabled();
        await expect(fixture.heading).toContainText('94%');

        releaseIdentity();
        await expect(fixture.heading).not.toContainText('%');
        await expect(correct).toBeEnabled();
        expect(fixture.lists()).toBe(3);
    });
}
