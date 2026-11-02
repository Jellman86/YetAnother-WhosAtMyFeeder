import { test, expect, type Page } from '@playwright/test';

type Taxon = {
    taxon_id: number; rank: string; scientific_name: string; name: string | null; source: string;
    principal: boolean; parent_id: number | null; species_count: number; seen_species: number; seen_count: number;
};

const t = (taxon_id: number, rank: string, scientific_name: string, name: string | null, parent_id: number | null,
    species_count: number, seen_species = 0, seen_count = 0, principal = true): Taxon => ({
    taxon_id, rank, scientific_name, name, source: rank === 'kingdom' || rank === 'phylum' || rank === 'class' ? 'catalogue-of-life' : 'ioc-world-bird-list',
    principal, parent_id, species_count, seen_species, seen_count
});

const lineage = [
    t(1, 'kingdom', 'Animalia', null, null, 11276, 3, 338),
    t(2, 'phylum', 'Chordata', null, 1, 11276, 3, 338),
    t(3, 'megaclass', 'Tetrapoda', null, 2, 11276, 3, 338, false),
    t(10, 'class', 'Aves', null, 3, 11276, 3, 338),
    t(20, 'order', 'Passeriformes', null, 10, 6700, 2, 335),
    t(30, 'family', 'Prunellidae', 'Accentors', 20, 13, 1, 324),
    t(40, 'genus', 'Prunella', null, 30, 13, 1, 324),
    t(50, 'species', 'Prunella modularis', 'Dunnock', 40, 1, 1, 324)
];
const orders = [
    t(21, 'order', 'Struthioniformes', null, 10, 2), t(22, 'order', 'Columbiformes', null, 10, 350, 1, 3),
    t(23, 'order', 'Piciformes', null, 10, 480), lineage[4]
];
const families = [
    t(31, 'family', 'Corvidae', 'Crows, Jays', 20, 130), t(32, 'family', 'Paridae', 'Tits, Chickadees', 20, 64, 1, 11),
    lineage[5], t(33, 'family', 'Turdidae', 'Thrushes', 20, 170)
];
const genera = [lineage[6]];
const species = [t(51, 'species', 'Prunella collaris', 'Alpine Accentor', 40, 1), lineage[7], t(52, 'species', 'Prunella montanella', 'Siberian Accentor', 40, 1)];
const columbidae = [t(60, 'family', 'Columbidae', 'Pigeons, Doves', 22, 350, 1, 3)];
const children: Record<number, Taxon[]> = { 10: orders, 20: families, 30: genera, 40: species, 22: columbidae, 60: [] };

// A plain image standing in for a Wikimedia reference photograph.
const PICTURE = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="3"><rect width="4" height="3" fill="#6b8e23"/></svg>';
const REFERENCE = 'https://upload.wikimedia.org/wikipedia/commons/thumb/dunnock.jpg';

async function prepare(page: Page, path = '/browser-tests/family-tree.html', familyName = 'Accentors', shuffle = false) {
    const errors: string[] = [];
    const infoRequests: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route(REFERENCE, (route) => route.fulfill({ contentType: 'image/svg+xml', body: PICTURE }));
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const url = new URL(route.request().url());
        const info = url.pathname.match(/^\/api\/species\/(.+)\/info$/);
        if (info) {
            const name = decodeURIComponent(info[1]);
            infoRequests.push(name);
            return route.fulfill({ json: { title: name, scientific_name: name, thumbnail_url: name === 'Prunella modularis' ? REFERENCE : null, source: 'Wikipedia' } });
        }
        if (url.pathname === '/api/taxonomy/lineage') {
            if (url.searchParams.get('scientific_name') !== 'Prunella modularis') return route.fulfill({ status: 404, json: { detail: 'Species not in the catalogue' } });
            const named = lineage.map((taxon) => (taxon.rank === 'family' ? { ...taxon, name: familyName } : taxon));
            // A source that lists ranks out of order must still read from the top down.
            return route.fulfill({ json: { lineage: shuffle ? [named[7], named[2], named[4], named[0], named[6], named[3], named[5], named[1]] : named } });
        }
        const match = url.pathname.match(/^\/api\/taxonomy\/(\d+)\/children$/);
        if (match) return route.fulfill({ json: { parent_id: Number(match[1]), children: children[Number(match[1])] ?? [] } });
        throw new Error(`Unexpected family tree fixture request: ${url}`);
    });
    await page.goto(path);
    return { errors, infoRequests };
}

test('the detection card shows the lineage from class to species, with context, and opens the tree', async ({ page }) => {
    const { errors } = await prepare(page);
    const card = page.locator('[data-taxonomy-lineage]');
    await expect(card).toBeVisible();
    await expect(card.locator('li')).toHaveText([/Class\s*Aves/, /Order\s*Passeriformes/, /Family\s*Accentors/, /Genus\s*Prunella/, /Species\s*Dunnock/]);
    await expect(card.locator('[aria-current="true"]')).toContainText('Dunnock');
    await expect(page.locator('[data-taxonomy-lineage-context]')).toHaveText('Accentors: 13 species worldwide, 1 seen at this feeder.');
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const dialog = page.getByRole('dialog', { name: 'Family tree of Dunnock' });
    await expect(dialog).toBeVisible();
    await expect(dialog.locator('[data-family-tree-breadcrumb] li')).toHaveText([/Kingdom\s*Animalia/, /Phylum\s*Chordata/]);
    await expect(dialog.locator('[data-family-tree-subtitle]')).toHaveText('Prunella modularis');
    expect(errors).toEqual([]);
});

test('the tree opens on the path to the bird, shows what was seen here and sums the rest', async ({ page }) => {
    await prepare(page);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const svg = page.locator('[data-family-tree-svg="tree"]');
    await expect(svg).toBeVisible();
    // The path, the seen pigeon order and tit family, and one "more" node per open branch.
    for (const id of ['10', '20', '30', '40', '50', '22', '32']) await expect(svg.locator(`[data-family-tree-node="${id}"]`)).toHaveCount(1);
    await expect(svg.locator('[data-family-tree-node="21"]')).toHaveCount(0);
    await expect(svg.getByRole('treeitem', { name: '2 more' })).toHaveCount(3);
    await expect(svg.getByRole('treeitem', { name: /Dunnock, Prunella modularis, Species, 324 captures here, this bird/ })).toHaveCount(1);
    // Every group says how big it is and what was seen of it, in the same words.
    await expect(svg.getByRole('treeitem', { name: /Columbiformes, Order, 350 species, 1 seen here/ })).toHaveCount(1);
    await expect(svg.getByRole('treeitem', { name: /Accentors, Prunellidae, Family, 13 species, 1 seen here/ })).toHaveCount(1);
    // The orders branch "more" opens every order in source order.
    await svg.locator('[data-family-tree-node="more:10"]').click();
    await expect(svg.locator('[data-family-tree-node="21"]')).toHaveCount(1);
    // A closed branch loads on demand when opened, and closes again.
    const pigeons = svg.locator('[data-family-tree-node="22"]');
    await expect(pigeons).toHaveAttribute('aria-expanded', 'false');
    await pigeons.click();
    await expect(svg.locator('[data-family-tree-node="60"]')).toHaveCount(1);
    await pigeons.press('Enter');
    await expect(svg.locator('[data-family-tree-node="60"]')).toHaveCount(0);
});

test('every node in the tree is a full 44px row to click, label and gap included', async ({ page }) => {
    await prepare(page);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const hits = page.locator('[data-family-tree-svg="tree"] [data-family-tree-hit]');
    await expect(hits.first()).toBeAttached();
    const heights = await hits.evaluateAll((rects) => rects.map((rect) => rect.getBoundingClientRect().height));
    expect(Math.min(...heights)).toBeGreaterThanOrEqual(44);
    // Neither a node's hit area nor its neighbour's covers the other: rows abut and never overlap.
    const boxes = await hits.evaluateAll((rects) => rects.map((rect) => {
        const { left, right, top, bottom } = rect.getBoundingClientRect();
        return { left, right, top: Math.round(top), bottom: Math.round(bottom) };
    }));
    for (const [index, a] of boxes.entries()) {
        for (const b of boxes.slice(index + 1)) {
            const overlaps = a.left < b.right && b.left < a.right && a.top < b.bottom - 1 && b.top < a.bottom - 1;
            expect(overlaps).toBe(false);
        }
    }
});

test('the fan and the outline show the same tree, the outline as a tree of disclosure items, and Escape closes', async ({ page }) => {
    await prepare(page);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    await page.locator('[data-family-tree-mode="fan"]').click();
    await expect(page.locator('[data-family-tree-svg="fan"] [data-family-tree-node="50"]')).toHaveCount(1);
    await page.locator('[data-family-tree-mode="outline"]').click();
    const outline = page.locator('[data-family-tree-outline]');
    await expect(outline.getByRole('treeitem', { name: /Dunnock/ })).toHaveAttribute('aria-current', 'true');
    await expect(outline.getByRole('treeitem', { name: /Passeriformes/ })).toHaveAttribute('aria-expanded', 'true');
    await expect(outline.getByRole('treeitem', { name: /Prunella,/ })).toHaveAttribute('aria-level', '4');
    await outline.getByRole('treeitem', { name: /Passeriformes/ }).click();
    await expect(outline.getByRole('treeitem', { name: /Dunnock/ })).toHaveCount(0);
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-family-tree]')).toHaveCount(0);
});

test('a bird the catalogue does not hold shows nothing rather than an error', async ({ page }) => {
    const { errors } = await prepare(page, '/browser-tests/family-tree.html?name=Nonexistus%20maximus');
    await expect(page.locator('[data-taxonomy-lineage]')).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('the card and the tree fit a 320px phone, one rank per row even with a long family name', async ({ page }, testInfo) => {
    await page.setViewportSize({ width: 320, height: 760 });
    await prepare(page, undefined, 'Chats, Old World Flycatchers');
    await expect(page.locator('[data-taxonomy-lineage]')).toBeVisible();
    const rows = page.locator('[data-taxonomy-lineage] li');
    const tops = await rows.evaluateAll((items) => items.map((item) => item.getBoundingClientRect().top));
    expect(tops).toEqual([...tops].sort((a, b) => a - b));
    const heights = await rows.evaluateAll((items) => items.map((item) => Math.round(item.getBoundingClientRect().height)));
    expect(Math.max(...heights) - Math.min(...heights)).toBeLessThanOrEqual(4);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('family-tree-card-320.png'), fullPage: true });
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    // A phone opens on the outline until the reader picks a layout.
    await expect(page.locator('[data-family-tree-outline]')).toBeVisible();
    await expect(page.locator('[data-family-tree-mode="outline"]')).toHaveAttribute('aria-pressed', 'true');
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.screenshot({ path: testInfo.outputPath('family-tree-320.png') });
});

test('a name opens its card on hover and keyboard focus: a species with its reference photo, a group with its size', async ({ page }) => {
    const { errors, infoRequests } = await prepare(page);
    const card = page.locator('[data-taxon-card]');
    const dunnock = page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' });
    await dunnock.hover();
    await expect(card).toBeVisible();
    await expect(card).toHaveAttribute('aria-label', 'Dunnock');
    await expect(card.locator('[data-taxon-card-picture]')).toHaveAttribute('src', REFERENCE);
    await expect(card.locator('[data-taxon-card-seen]')).toHaveText('324 captures here');
    await expect(dunnock).toHaveAttribute('aria-expanded', 'true');
    // The pointer may travel into the card without it closing.
    await card.hover();
    await expect(card).toBeVisible();
    await page.mouse.move(5, 700);
    await expect(card).toHaveCount(0);
    // A group has no picture: it says how big it is and what was seen of it.
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Accentors' }).hover();
    await expect(card).toHaveAttribute('aria-label', 'Accentors');
    await expect(card.locator('[data-taxon-card-picture], [data-taxon-card-no-picture]')).toHaveCount(0);
    await expect(card.locator('[data-taxon-card-seen]')).toHaveText('13 species worldwide, 1 seen here');
    await page.mouse.move(5, 700);
    await expect(card).toHaveCount(0);
    // Keyboard focus opens it at once, and Escape closes it.
    await page.locator('[data-taxonomy-ladder] li[data-taxon-rank="genus"] button').focus();
    await page.keyboard.press('Tab');
    await expect(card).toHaveAttribute('aria-label', 'Dunnock');
    await page.keyboard.press('Escape');
    await expect(card).toHaveCount(0);
    // Looking again costs no second request.
    await dunnock.hover();
    await expect(card.locator('[data-taxon-card-picture]')).toBeVisible();
    expect(infoRequests).toEqual(['Prunella modularis']);
    expect(errors).toEqual([]);
});

test('a species card still shows its photo when it is pinned while the photo is loading', async ({ page }) => {
    const { errors } = await prepare(page);
    // Hold the lookup so the card is still loading when the same name is clicked.
    let release: () => void = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route(/\/api\/species\/.+\/info$/, async (route) => {
        await held;
        await route.fulfill({ json: { title: 'Prunella modularis', scientific_name: 'Prunella modularis', thumbnail_url: REFERENCE } });
    });
    const card = page.locator('[data-taxon-card]');
    const dunnock = page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' });
    await dunnock.hover();
    await expect(card).toHaveAttribute('aria-label', 'Dunnock');
    // Pinning places the same species again; the lookup already under way must still land.
    await dunnock.click();
    release();
    await expect(card.locator('[data-taxon-card-picture]')).toHaveAttribute('src', REFERENCE);
    expect(errors).toEqual([]);
});

test('a click pins the card until a click elsewhere, so a tap can open it', async ({ page }) => {
    await prepare(page);
    const card = page.locator('[data-taxon-card]');
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' }).click();
    await expect(card).toBeVisible();
    await page.mouse.move(5, 700);
    await expect(card).toBeVisible();
    await page.mouse.click(5, 700);
    await expect(card).toHaveCount(0);
});

test('in the tree a species opens its card, a species without a photo says so, and Escape closes the card before the tree', async ({ page }) => {
    await prepare(page);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const svg = page.locator('[data-family-tree-svg="tree"]');
    const card = page.locator('[data-taxon-card]');
    await svg.locator('[data-family-tree-node="more:40"]').click();
    await svg.locator('[data-family-tree-node="51"]').click();
    await expect(card).toHaveAttribute('aria-label', 'Alpine Accentor');
    await expect(card.locator('[data-taxon-card-no-picture]')).toHaveText('No reference photo');
    await expect(card.locator('[data-taxon-card-seen]')).toHaveText('Not seen at this feeder yet');
    // A species has nothing to open, so it is a leaf of the tree, not a disclosure.
    await expect(svg.locator('[data-family-tree-node="51"]')).not.toHaveAttribute('aria-expanded');
    await page.keyboard.press('Escape');
    await expect(card).toHaveCount(0);
    await expect(page.locator('[data-family-tree]')).toBeVisible();
    // Opening a group closes any card and still opens the branch.
    await svg.locator('[data-family-tree-node="50"]').click();
    await expect(card).toHaveAttribute('aria-label', 'Dunnock');
    await svg.locator('[data-family-tree-node="22"]').click();
    await expect(card).toHaveCount(0);
    await expect(svg.locator('[data-family-tree-node="60"]')).toHaveCount(1);
    await page.keyboard.press('Escape');
    await expect(page.locator('[data-family-tree]')).toHaveCount(0);
});

/** Whether each name in a ladder row is set in italics, read from the rendered style. */
async function italics(page: Page, rank: string) {
    await expect(page.locator('[data-taxonomy-ladder]')).toBeVisible();
    return page.locator(`[data-taxonomy-ladder] li[data-taxon-rank="${rank}"] [data-taxon-name]`).evaluateAll((names) =>
        names.map((name) => ({
            kind: name.getAttribute('data-taxon-name'),
            text: name.textContent,
            italic: [...name.childNodes].some((child) => child instanceof Element && getComputedStyle(child).fontStyle === 'italic')
        }))
    );
}

test('only the genus and the ranks beneath it are set in italics, never a common name', async ({ page }) => {
    await prepare(page);
    expect(await italics(page, 'class')).toEqual([{ kind: 'scientific', text: 'Aves', italic: false }]);
    expect(await italics(page, 'order')).toEqual([{ kind: 'scientific', text: 'Passeriformes', italic: false }]);
    expect(await italics(page, 'family')).toEqual([
        { kind: 'common', text: 'Accentors', italic: false },
        { kind: 'scientific', text: 'Prunellidae', italic: false }
    ]);
    expect(await italics(page, 'genus')).toEqual([{ kind: 'scientific', text: 'Prunella', italic: true }]);
    expect(await italics(page, 'species')).toEqual([
        { kind: 'common', text: 'Dunnock', italic: false },
        { kind: 'scientific', text: 'Prunella modularis', italic: true }
    ]);

    // The card and the tree follow the same rule.
    await page.locator('[data-taxonomy-ladder] button', { hasText: 'Accentors' }).hover();
    await expect(page.locator('[data-taxon-card] [data-taxon-name="scientific"] i')).toHaveCount(0);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const svg = page.locator('[data-family-tree-svg="tree"]');
    await expect(svg.locator('[data-family-tree-node="40"]')).toBeVisible();
    const label = (id: number) => svg.locator(`[data-family-tree-node="${id}"] tspan[font-style="italic"]`);
    await expect(label(40)).toHaveText(['Prunella']);
    await expect(label(50)).toHaveText(['Prunella modularis']);
    for (const id of [10, 20, 30, 32]) await expect(label(id)).toHaveCount(0);
});

test('the strictly scientific naming style leads with italic binomials and upright family names', async ({ page }) => {
    await prepare(page, '/browser-tests/family-tree.html?style=scientific');
    expect(await italics(page, 'family')).toEqual([{ kind: 'scientific', text: 'Prunellidae', italic: false }]);
    expect(await italics(page, 'species')).toEqual([{ kind: 'scientific', text: 'Prunella modularis', italic: true }]);
    await expect(page.locator('[data-taxonomy-ladder] [data-taxon-name="common"]')).toHaveCount(0);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    await expect(page.getByRole('dialog', { name: 'Family tree of Prunella modularis' })).toBeVisible();
});

test('ranks read from the class down in the ladder, the tree columns and the breadcrumb, whatever order they arrive in', async ({ page }) => {
    await prepare(page, undefined, 'Accentors', true);
    await expect(page.locator('[data-taxonomy-ladder] li')).toHaveText([/Class/, /Order/, /Family/, /Genus/, /Species/]);
    await expect(page.locator('[data-taxonomy-ladder] li').last()).toHaveAttribute('aria-current', 'true');
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    await expect(page.locator('[data-family-tree-rank-heading]')).toHaveText(['Class', 'Order', 'Family', 'Genus', 'Species']);
    await expect(page.locator('[data-family-tree-breadcrumb] li')).toHaveText([/Kingdom\s*Animalia/, /Phylum\s*Chordata/]);
});

for (const mode of ['tree', 'outline'] as const) {
    test(`the ${mode} is one tab stop that the arrow keys move through, opening each card on the way`, async ({ page }) => {
        await prepare(page);
        await page.getByRole('button', { name: 'Open the family tree' }).click();
        await page.locator(`[data-family-tree-mode="${mode}"]`).click();
        const tree = page.getByRole('tree');
        const card = page.locator('[data-taxon-card]');
        const node = (id: string | number) => tree.locator(`[data-family-tree-node="${id}"]`);
        await expect(node(50)).toBeVisible();
        await expect(tree.locator('[tabindex="0"]')).toHaveCount(1);

        // Tab from the last header control lands on the bird itself, and its card opens.
        await page.locator('[data-family-tree-close]').focus();
        await page.keyboard.press('Tab');
        await expect(node(50)).toBeFocused();
        await expect(card).toHaveAttribute('aria-label', 'Dunnock');

        // Left steps out to the genus; Left again closes it, Right opens it, Right again steps in.
        await page.keyboard.press('ArrowLeft');
        await expect(node(40)).toBeFocused();
        await expect(card).toHaveAttribute('aria-label', 'Prunella');
        await page.keyboard.press('ArrowLeft');
        await expect(node(40)).toHaveAttribute('aria-expanded', 'false');
        await expect(node(50)).toHaveCount(0);
        await page.keyboard.press('ArrowRight');
        await expect(node(40)).toHaveAttribute('aria-expanded', 'true');
        await page.keyboard.press('ArrowRight');
        await expect(node(50)).toBeFocused();

        // Home and End reach the ends; Down walks the visible nodes in reading order.
        await page.keyboard.press('Home');
        await expect(node(10)).toBeFocused();
        await page.keyboard.press('ArrowDown');
        await expect(node(22)).toBeFocused();
        await expect(card).toHaveAttribute('aria-label', 'Columbiformes');
        await page.keyboard.press('End');
        await expect(node('more:10')).toBeFocused();

        // Enter on a "more" node shows the rest and keeps focus in the branch.
        await page.keyboard.press('Enter');
        await expect(node(21)).toBeFocused();
        await expect(tree.locator('[tabindex="0"]')).toHaveCount(1);

        // Escape closes the card first, then the tree.
        await page.keyboard.press('Escape');
        await expect(card).toHaveCount(0);
        await page.keyboard.press('Escape');
        await expect(page.locator('[data-family-tree]')).toHaveCount(0);
    });
}

test('a node in the tree opens its card on hover, with the group size and what was seen of it', async ({ page }) => {
    await prepare(page);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const card = page.locator('[data-taxon-card]');
    await page.locator('[data-family-tree-svg="tree"] [data-family-tree-node="32"]').hover();
    await expect(card).toHaveAttribute('aria-label', 'Tits, Chickadees');
    await expect(card.locator('[data-taxon-card-rank]')).toHaveText('Family');
    // The card sits under the node's marker, not under the middle of its wide click target.
    const [cardBox, markerBox] = await Promise.all([
        card.boundingBox(),
        page.locator('[data-family-tree-svg="tree"] [data-family-tree-node="32"] [data-tree-anchor]').boundingBox()
    ]);
    expect(Math.abs((cardBox?.x ?? 0) + (cardBox?.width ?? 0) / 2 - ((markerBox?.x ?? 0) + (markerBox?.width ?? 0) / 2))).toBeLessThan(4);
    await expect(card.locator('[data-taxon-card-seen]')).toHaveText('64 species worldwide, 1 seen here');
    // The bird's own card names it as this bird and credits its reference photo.
    await page.locator('[data-family-tree-svg="tree"] [data-family-tree-node="50"]').hover();
    await expect(card).toHaveAttribute('aria-label', 'Dunnock');
    await expect(card.locator('[data-taxon-card-rank]')).toHaveText('Species · This bird');
    await expect(card.locator('[data-taxon-card-attribution]')).toHaveText('Reference photo: Wikipedia');
});

test('a Garden animal gets the same tree without a claim about bird visits', async ({ page }) => {
    const { errors } = await prepare(page, '/browser-tests/family-tree.html?subject=animal');
    await expect(page.locator('[data-taxonomy-lineage-context]')).toHaveCount(0);
    await page.locator('[data-taxonomy-ladder] li[data-taxon-rank="family"] button').hover();
    await expect(page.locator('[data-taxon-card]')).toBeVisible();
    await expect(page.locator('[data-taxon-card-seen]')).toHaveCount(0);
    await page.mouse.move(5, 700);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const legend = page.locator('[data-family-tree-legend]');
    await expect(legend).toContainText('This animal');
    await expect(legend).toContainText('Path to this animal');
    await expect(legend).not.toContainText('Seen at this feeder');
    const svg = page.locator('[data-family-tree-svg="tree"]');
    await expect(svg.getByRole('treeitem', { name: /Dunnock, Prunella modularis, Species, this animal$/ })).toHaveCount(1);
    await expect(svg.getByRole('treeitem', { name: /seen here/ })).toHaveCount(0);
    await expect(page.locator('[data-family-tree] footer')).toContainText('SpeciesNet taxonomy');
    expect(errors).toEqual([]);
});
