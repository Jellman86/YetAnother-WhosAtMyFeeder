import { test, expect, type Page } from '@playwright/test';

type Taxon = {
    taxon_id: number; rank: string; scientific_name: string; name: string | null; source: string;
    principal: boolean; parent_id: number | null; species_count: number; seen_species: number; seen_count: number;
    authorship?: string | null;
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
    { ...t(50, 'species', 'Prunella modularis', 'Dunnock', 40, 1, 1, 324), authorship: '(Linnaeus, 1758)' }
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
// A Garden animal's lineage, as the lineage route returns it: SpeciesNet stores "red fox", and the
// route cases it as the Garden record does. Its sizes are the model's, not the world's.
const animalLineage = [
    t(1, 'kingdom', 'Animalia', null, null, 3539, 2, 31),
    t(2, 'phylum', 'Chordata', null, 1, 3539, 2, 31),
    t(70, 'class', 'Mammalia', 'Mammal', 2, 600, 2, 31),
    t(71, 'order', 'Carnivora', 'Carnivorous Mammal', 70, 120, 1, 27),
    t(72, 'family', 'Canidae', 'Canine Family', 71, 20, 1, 27),
    t(73, 'genus', 'Vulpes', null, 72, 6, 1, 27),
    t(74, 'species', 'Vulpes vulpes', 'Red Fox', 73, 1, 1, 27)
];
const children: Record<number, Taxon[]> = {
    10: orders, 20: families, 30: genera, 40: species, 22: columbidae, 60: [],
    70: [animalLineage[3], t(75, 'order', 'Rodentia', 'Rodent', 70, 200)], 71: [animalLineage[4]], 72: [animalLineage[5]], 73: [animalLineage[6]]
};

type Photo = { url: string; kind: 'camera' | 'garden'; species_id: number; scientific_name: string; name: string | null; taken_at: string };
type Facts = {
    taxon_id: number; rank: string; visits: number; species_seen: number; first_seen: string | null; last_seen: string | null;
    heard: number | null; last_heard: string | null; sources: string[]; photo: Photo | null;
};
const seen = (taxon_id: number, rank: string, visits: number, species_seen: number, first: string, last: string,
    heard: number | null = null, photo: Photo | null = null, sources = ['camera']): Facts => ({
    taxon_id, rank, visits, species_seen, first_seen: first, last_seen: last, heard, last_heard: heard ? last : null, sources, photo
});
const unseen = (taxon_id: number, rank: string): Facts => seen(taxon_id, rank, 0, 0, '', '', 0);
const FIRST = '2025-03-14T09:12:00Z';
const LAST = '2026-11-02T08:41:00Z';
const OWN = '/api/about/showcase/1793633976.87781-2kuz0c.jpg';
const OWN_DUNNOCK: Photo = { url: OWN, kind: 'camera', species_id: 50, scientific_name: 'Prunella modularis', name: 'Dunnock', taken_at: LAST };
const FOX_CROP: Photo = { url: `/api/garden/${'a'.repeat(32)}/crop`, kind: 'garden', species_id: 74, scientific_name: 'Vulpes vulpes', name: 'Red Fox', taken_at: LAST };
/** What the facts route says by default: visits and calls, and no photograph of this install's own. */
function defaultFacts(): Record<number, Facts> {
    const found: Record<number, Facts> = {};
    for (const [id, rank, visits, species] of [[1, 'kingdom', 47, 3], [2, 'phylum', 47, 3], [10, 'class', 47, 3], [20, 'order', 44, 2],
        [30, 'family', 41, 1], [40, 'genus', 41, 1], [50, 'species', 41, 1], [22, 'order', 3, 1], [32, 'family', 3, 1], [60, 'family', 3, 1]] as const) {
        found[id] = { ...seen(id, rank, visits, species, FIRST, LAST, id === 50 || id === 40 || id === 30 ? 1203 : 0) };
        if (rank !== 'species') found[id].first_seen = FIRST;
    }
    for (const [id, rank] of [[21, 'order'], [23, 'order'], [31, 'family'], [33, 'family'], [51, 'species'], [52, 'species']] as const) found[id] = unseen(id, rank);
    for (const [id, rank] of [[70, 'class'], [71, 'order'], [72, 'family'], [73, 'genus'], [74, 'species']] as const) {
        found[id] = seen(id, rank, 27, 1, '2026-05-02T22:10:00Z', '2026-11-01T23:40:00Z', null, null, ['garden']);
    }
    found[75] = unseen(75, 'order');
    return found;
}
// Long enough to need the card's three-line clamp at any width.
const FOX_SUMMARY = 'The red fox is the largest of the true foxes and one of the most widely distributed members of the order Carnivora, present across the entire Northern Hemisphere including most of North America, Europe and Asia, plus parts of North Africa. It is listed as least concern.';
const NAMES = [
    { language: 'fr', name: 'Accenteur mouchet', preferred: true },
    { language: 'fr', name: 'Mouchet', preferred: false },
    { language: 'de', name: 'Heckenbraunelle', preferred: true }
];

// A plain image standing in for a Wikimedia reference photograph.
const PICTURE = '<svg xmlns="http://www.w3.org/2000/svg" width="4" height="3"><rect width="4" height="3" fill="#6b8e23"/></svg>';
const REFERENCE = 'https://upload.wikimedia.org/wikipedia/commons/thumb/dunnock.jpg';

interface Options {
    /** Facts per taxon in place of the defaults; a missing id is one the catalogue does not hold. */
    facts?: Record<number, Facts>;
    scope?: { scope: 'all' | 'shared'; shared_days: number | null };
    /** Answer the facts route with a server error until this many requests have failed. */
    factsFailures?: number;
    conservation?: string | null;
}

async function prepare(page: Page, path = '/browser-tests/family-tree.html', familyName = 'Accentors', shuffle = false, options: Options = {}) {
    const errors: string[] = [];
    const infoRequests: string[] = [];
    const factsRequests: number[][] = [];
    const facts = options.facts ?? defaultFacts();
    let failures = options.factsFailures ?? 0;
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route(REFERENCE, (route) => route.fulfill({ contentType: 'image/svg+xml', body: PICTURE }));
    await page.route((url) => url.pathname.startsWith('/api/about/showcase/') || url.pathname.startsWith('/api/garden/'), (route) =>
        route.fulfill({ contentType: 'image/svg+xml', body: PICTURE }));
    await page.route((url) => url.pathname.startsWith('/api/') && !url.pathname.startsWith('/api/about/showcase/') && !url.pathname.startsWith('/api/garden/'), async (route) => {
        const url = new URL(route.request().url());
        const info = url.pathname.match(/^\/api\/species\/(.+)\/info$/);
        if (info) {
            const name = decodeURIComponent(info[1]);
            const rank = url.searchParams.get('rank');
            infoRequests.push(rank ? `${rank}:${name}` : name);
            if (rank) return route.fulfill({ json: { title: name, scientific_name: name, extract: `The ${name} family summary.`, summary_source: 'iNaturalist', thumbnail_url: REFERENCE } });
            return route.fulfill({ json: {
                title: name, scientific_name: name, thumbnail_url: name === 'Prunella modularis' ? REFERENCE : null, source: 'Wikipedia',
                extract: name === 'Prunella modularis' ? 'The dunnock is a small passerine.' : name === 'Vulpes vulpes' ? FOX_SUMMARY : null,
                summary_source: 'Wikipedia',
                conservation_status: options.conservation === undefined ? 'LC' : options.conservation
            } });
        }
        if (url.pathname === '/api/taxonomy/facts') {
            const ids = url.searchParams.getAll('ids').map(Number);
            factsRequests.push(ids);
            if (failures > 0) {
                failures -= 1;
                return route.fulfill({ status: 500, json: { detail: 'unavailable' } });
            }
            return route.fulfill({ json: { ...(options.scope ?? { scope: 'all', shared_days: null }), facts: ids.map((id) => facts[id]).filter(Boolean) } });
        }
        const names = url.pathname.match(/^\/api\/taxonomy\/(\d+)\/names$/);
        if (names) {
            const own = Number(names[1]) === 50 ? NAMES : [];
            return route.fulfill({ json: { taxon_id: Number(names[1]), names: own, languages: new Set(own.map((n) => n.language)).size, truncated: false } });
        }
        if (url.pathname === '/api/taxonomy/lineage') {
            if (url.searchParams.get('scientific_name') === 'Vulpes vulpes') return route.fulfill({ json: { lineage: animalLineage } });
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
    return { errors, infoRequests, factsRequests };
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
    await expect(svg.getByRole('treeitem', { name: /Dunnock, Prunella modularis, Species, 41 visits, heard by BirdNET, this bird/ })).toHaveCount(1);
    // Every group says how big it is and what was seen of it, in the same words.
    await expect(svg.getByRole('treeitem', { name: /Columbiformes, Order, 350 species, 1 seen here/ })).toHaveCount(1);
    await expect(svg.getByRole('treeitem', { name: /Accentors, Prunellidae, Family, 13 species, 1 seen here/ })).toHaveCount(1);
    // The orders branch "more" opens every order in source order.
    // The pointer still rests where the open button was; move it clear of any card it opened.
    await page.mouse.move(2, 2);
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
    await expect(card.locator('[data-fact="visits"]')).toHaveText('41');
    await expect(dunnock).toHaveAttribute('aria-expanded', 'true');
    // The pointer may travel into the card without it closing.
    await card.hover();
    await expect(card).toBeVisible();
    await page.mouse.move(5, 700);
    await expect(card).toHaveCount(0);
    // A group has no reference picture, only this install's own photo of a member, and here there is none:
    // it says how big it is and what was seen of it.
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Accentors' }).hover();
    await expect(card).toHaveAttribute('aria-label', 'Accentors');
    await expect(card.locator('[data-taxon-card-figure]')).toHaveCount(0);
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
    // The family's description is bound to its rank; neither lookup is asked twice.
    expect(infoRequests).toEqual(['Prunella modularis', 'family:Prunellidae']);
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
    await expect(card.locator('[data-taxon-card-visits]')).toHaveText('No visits recorded');
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
    // The bird's own card names it as this bird. Its photo is captioned generically: the lookup's
    // `source` is the summary provider and may not be where the photograph came from.
    await page.locator('[data-family-tree-svg="tree"] [data-family-tree-node="50"]').hover();
    await expect(card).toHaveAttribute('aria-label', 'Dunnock');
    await expect(card.locator('[data-taxon-card-rank]')).toHaveText('Species · This bird');
    await expect(card.locator('[data-taxon-card-caption]')).toHaveText('Reference photo');
});

test('a Garden animal gets the same tree with its own Garden visits and no worldwide counts', async ({ page }) => {
    const { errors } = await prepare(page, '/browser-tests/family-tree.html?name=Vulpes%20vulpes&subject=animal', undefined, false, {
        facts: { ...defaultFacts(), 72: { ...defaultFacts()[72], photo: FOX_CROP }, 74: { ...defaultFacts()[74], photo: FOX_CROP } }
    });
    // The animal is named as the Garden record names it, in the ladder, the tree, its card and a group's caption.
    await expect(page.locator('[data-taxonomy-ladder] li[data-taxon-rank="species"] [data-taxon-name="common"]')).toHaveText('Red Fox');
    await expect(page.locator('[data-taxonomy-ladder] li[data-taxon-rank="species"] [data-taxon-name="scientific"]')).toHaveText('Vulpes vulpes');
    // SpeciesNet's group sizes are the model's, so the record makes no worldwide claim.
    await expect(page.locator('[data-taxonomy-lineage-context]')).toHaveCount(0);
    await page.locator('[data-taxonomy-ladder] li[data-taxon-rank="family"] button').hover();
    const card = page.locator('[data-taxon-card]');
    await expect(card.locator('[data-taxon-card-seen]')).toHaveText('1 seen here');
    await expect(card).not.toContainText('worldwide');
    await page.mouse.move(5, 700);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const legend = page.locator('[data-family-tree-legend]');
    await expect(legend).toContainText('This animal');
    await expect(legend).toContainText('Seen here');
    await expect(legend).not.toContainText('at this feeder');
    const svg = page.locator('[data-family-tree-svg="tree"]');
    await expect(page.getByRole('dialog', { name: 'Family tree of Red Fox' })).toBeVisible();
    await expect(svg.getByRole('treeitem', { name: /Red Fox, Vulpes vulpes, Species, 27 visits, this animal$/ })).toHaveCount(1);
    await expect(svg.getByRole('treeitem', { name: /Canine Family, Canidae, Family, 1 seen here$/ })).toHaveCount(1);
    await expect(svg.locator('[data-family-tree-node="72"] [data-family-tree-label]')).toHaveText('Canine Family');
    // Its own Garden crop is the node's thumbnail and the card's photograph.
    await expect(svg.locator('[data-family-tree-node="74"] [data-family-tree-photo]')).toHaveAttribute('href', FOX_CROP.url);
    await svg.locator('[data-family-tree-node="74"]').hover();
    await expect(card).toHaveAttribute('aria-label', 'Red Fox');
    await expect(card.locator('[data-taxon-card-own-picture]')).toHaveAttribute('src', FOX_CROP.url);
    await expect(card.locator('[data-taxon-card-own-picture]')).toHaveAttribute('alt', 'Your photograph of Red Fox');
    await expect(card.locator('[data-fact="visits"]')).toHaveText('27');
    await page.mouse.move(2, 2);
    await expect(card).toHaveCount(0);
    await svg.locator('[data-family-tree-node="72"]').hover();
    await expect(card.locator('[data-taxon-card-caption]')).toHaveText('Your photo of Red Fox');
    await expect(page.locator('[data-family-tree] [data-family-tree-source]')).toContainText('SpeciesNet taxonomy');
    expect(errors).toEqual([]);
});

test("a species card leads with this install's own photo, and falls back to the reference photo when it cannot load", async ({ page }) => {
    const facts = { ...defaultFacts(), 50: { ...defaultFacts()[50], photo: OWN_DUNNOCK } };
    await prepare(page, undefined, undefined, false, { facts });
    const card = page.locator('[data-taxon-card]');
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' }).hover();
    await expect(card.locator('[data-taxon-card-own-picture]')).toHaveAttribute('src', OWN);
    await expect(card.locator('[data-taxon-card-own-picture]')).toHaveAttribute('alt', 'Your photograph of Dunnock');
    await expect(card.locator('[data-taxon-card-caption]')).toHaveText('Your photo, 2 Nov 2026');
    await page.mouse.move(5, 700);
    await expect(card).toHaveCount(0);

    // A photograph withdrawn since (hidden, or no longer shared) gives way to the reference photo.
    await page.route(OWN, (route) => route.fulfill({ status: 404, body: '' }));
    await page.reload();
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' }).hover();
    await expect(card.locator('[data-taxon-card-picture]')).toHaveAttribute('src', REFERENCE);
    await expect(card.locator('[data-taxon-card-caption]')).toHaveText('Reference photo');
});

test('a species card states its visits, first and last seen, calls heard, authority and IUCN category', async ({ page }) => {
    const { errors } = await prepare(page);
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' }).hover();
    const card = page.locator('[data-taxon-card]');
    await expect(card.locator('[data-fact="visits"]')).toHaveText('41');
    await expect(card.locator('[data-fact="first"]')).toHaveText('14 Mar 2025');
    await expect(card.locator('[data-fact="last"]')).toHaveText('2 Nov 2026');
    await expect(card.locator('[data-taxon-card-scope]')).toHaveText('Counts cover all history');
    await expect(card.locator('[data-taxon-card-heard]')).toHaveText(/Heard\s*1,203 calls/);
    // A category in words with its code, so it never rests on a colour.
    await expect(card.locator('[data-taxon-card-iucn]')).toHaveText(/IUCN\s*Least concern \(LC\)/);
    // The authority as stored, upright after the italic binomial.
    const authority = card.locator('[data-taxon-authority]');
    await expect(authority).toHaveText('(Linnaeus, 1758)');
    expect(await authority.evaluate((element) => getComputedStyle(element).fontStyle)).toBe('normal');
    await expect(card.locator('[data-taxon-name="scientific"] i')).toHaveText('Prunella modularis');
    await expect(card.locator('[data-taxon-card-description]')).toContainText('The dunnock is a small passerine.');
    // A group with no authority recorded shows none.
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Accentors' }).hover();
    await expect(card).toHaveAttribute('aria-label', 'Accentors');
    await expect(card.locator('[data-taxon-authority]')).toHaveCount(0);
    expect(errors).toEqual([]);
});

test('an unknown status is left out, and a species never seen says so in words', async ({ page }) => {
    await prepare(page, undefined, undefined, false, { conservation: null, facts: { ...defaultFacts(), 50: { ...unseen(50, 'species'), heard: 0 } } });
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' }).hover();
    const card = page.locator('[data-taxon-card]');
    await expect(card.locator('[data-taxon-card-visits]')).toHaveText('No visits recorded');
    await expect(card.locator('[data-taxon-card-iucn], [data-taxon-card-heard]')).toHaveCount(0);
});

test('a pinned card takes Tab into its names, which open and close, and Escape returns to the name', async ({ page }) => {
    await prepare(page);
    const dunnock = page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' });
    await dunnock.focus();
    await page.keyboard.press('Enter');
    const card = page.locator('[data-taxon-card]');
    const names = card.locator('[data-taxon-card-names]');
    await expect(names.locator('summary')).toHaveText('Names in 2 languages');
    await expect(names).not.toHaveAttribute('open');
    await page.keyboard.press('Tab');
    await expect(names.locator('summary')).toBeFocused();
    await page.keyboard.press('Enter');
    await expect(names).toHaveAttribute('open');
    // Languages named in the reader's language, each with its preferred name first.
    await expect(names.locator('dt')).toHaveText(['French', 'German']);
    await expect(names.locator('dd')).toHaveText(['Accenteur mouchet, Mouchet', 'Heckenbraunelle']);
    await page.keyboard.press('Enter');
    await expect(names).not.toHaveAttribute('open');
    await page.keyboard.press('Escape');
    await expect(card).toHaveCount(0);
    await expect(dunnock).toBeFocused();
});

test('a family node rolls up what was seen beneath it, pictured by its most-seen member, with its description', async ({ page }) => {
    const facts = { ...defaultFacts(), 30: { ...defaultFacts()[30], photo: OWN_DUNNOCK } };
    const { infoRequests } = await prepare(page, undefined, undefined, false, { facts });
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    await page.locator('[data-family-tree-svg="tree"] [data-family-tree-node="30"]').hover();
    const card = page.locator('[data-taxon-card]');
    await expect(card).toHaveAttribute('aria-label', 'Accentors');
    await expect(card.locator('[data-taxon-card-seen]')).toHaveText('13 species worldwide, 1 seen here');
    await expect(card.locator('[data-fact="visits"]')).toHaveText('41');
    await expect(card.locator('[data-fact="last"]')).toHaveText('2 Nov 2026');
    await expect(card.locator('[data-taxon-card-caption]')).toHaveText('Your photo of Dunnock');
    await expect(card.locator('[data-taxon-card-description]')).toContainText('The Prunellidae family summary.');
    await expect(card.locator('[data-taxon-card-description]')).toContainText('From iNaturalist');
    // A genus is never described: its name can belong to a plant too.
    await page.mouse.move(2, 2);
    await expect(card).toHaveCount(0);
    await page.locator('[data-family-tree-svg="tree"] [data-family-tree-node="40"]').hover();
    await expect(card).toHaveAttribute('aria-label', 'Prunella');
    await expect(card.locator('[data-taxon-card-description]')).toHaveCount(0);
    expect(infoRequests).not.toContain('genus:Prunella');
});

test('species nodes show the own photo, visits and heard, and each open level is one bounded facts request', async ({ page }) => {
    const facts = { ...defaultFacts(), 50: { ...defaultFacts()[50], photo: OWN_DUNNOCK } };
    const { factsRequests } = await prepare(page, undefined, undefined, false, { facts });
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const svg = page.locator('[data-family-tree-svg="tree"]');
    await expect(svg.locator('[data-family-tree-node="50"] [data-family-tree-photo]')).toHaveAttribute('href', OWN);
    await expect(svg.locator('[data-family-tree-node="50"]')).toContainText('41 visits');
    await expect(svg.locator('[data-family-tree-node="50"] [data-family-tree-heard]')).toHaveText('heard');
    await expect(page.locator('[data-family-tree-scope]')).toHaveText('Counts cover all history');
    await page.locator('[data-family-tree-mode="outline"]').click();
    await expect(page.locator('[data-family-tree-outline] [data-family-tree-node="50"] [data-family-tree-photo]')).toHaveAttribute('src', OWN);
    // The path once, then each opened branch's shown taxa; no taxon is asked about twice.
    const asked = factsRequests.flat();
    expect(new Set(asked).size).toBe(asked.length);
    expect(Math.max(...factsRequests.map((ids) => ids.length))).toBeLessThanOrEqual(100);
    expect(factsRequests.length).toBeLessThanOrEqual(6);
});

test('a visitor reads the shared window: no calls or own photos unless shared, and the window is named', async ({ page }) => {
    const shared = defaultFacts();
    for (const entry of Object.values(shared)) {
        entry.heard = null;
        entry.last_heard = null;
    }
    await prepare(page, undefined, undefined, false, { facts: shared, scope: { scope: 'shared', shared_days: 7 } });
    await page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' }).hover();
    const card = page.locator('[data-taxon-card]');
    await expect(card.locator('[data-taxon-card-scope]')).toHaveText('Counts cover the last 7 days shared with visitors');
    await expect(card.locator('[data-taxon-card-heard]')).toHaveCount(0);
    await expect(card.locator('[data-taxon-card-own-picture]')).toHaveCount(0);
    await expect(card.locator('[data-taxon-card-picture]')).toHaveAttribute('src', REFERENCE);
});

test('facts that fail to load say so, and Try again reads them', async ({ page }) => {
    await prepare(page, undefined, undefined, false, { factsFailures: 1 });
    const dunnock = page.locator('[data-taxonomy-lineage] button', { hasText: 'Dunnock' });
    await dunnock.click();
    const card = page.locator('[data-taxon-card]');
    await expect(card.locator('[data-taxon-card-facts-failed]')).toContainText('What was recorded here could not load.');
    await card.getByRole('button', { name: 'Try again' }).click();
    await expect(card.locator('[data-fact="visits"]')).toHaveText('41');
});

test('a card stays inside the family-tree dialog, even for a node near its foot', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 640 });
    const facts = defaultFacts();
    for (const id of [30, 50, 52]) facts[id] = { ...facts[id], ...seen(id, id === 30 ? 'family' : 'species', 41, 1, FIRST, LAST, 1203, OWN_DUNNOCK) };
    await prepare(page, undefined, undefined, false, { facts });
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    const svg = page.locator('[data-family-tree-svg="tree"]');
    await page.mouse.move(2, 2);
    await svg.locator('[data-family-tree-node="more:40"]').click();
    await page.mouse.move(2, 2);
    const dialog = await page.locator('[data-family-tree]').boundingBox();
    const card = page.locator('[data-taxon-card]');
    // The lowest species, the family, and the bird: each card inside the dialog, none over its own node.
    for (const id of [52, 30, 50]) {
        const node = svg.locator(`[data-family-tree-node="${id}"]`);
        await node.hover();
        await expect(card).toBeVisible();
        await expect(card.locator('[data-fact="visits"]')).toBeVisible();
        const [box, marker] = await Promise.all([card.boundingBox(), node.locator('[data-tree-anchor]').boundingBox()]);
        expect(box && dialog && marker).toBeTruthy();
        if (!box || !dialog || !marker) return;
        expect(box.y).toBeGreaterThanOrEqual(dialog.y);
        expect(box.y + box.height).toBeLessThanOrEqual(dialog.y + dialog.height);
        expect(box.x).toBeGreaterThanOrEqual(dialog.x);
        expect(box.x + box.width).toBeLessThanOrEqual(dialog.x + dialog.width);
        const covers = box.x < marker.x + marker.width && marker.x < box.x + box.width && box.y < marker.y + marker.height && marker.y < box.y + box.height;
        expect(covers).toBe(false);
        await page.mouse.move(2, 2);
        await expect(card).toHaveCount(0);
    }
});

test('a card that scrolls inside fades at its foot until its end, where the description and source show whole', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 560 });
    const facts = { ...defaultFacts(), 74: { ...defaultFacts()[74], photo: FOX_CROP } };
    await prepare(page, '/browser-tests/family-tree.html?name=Vulpes%20vulpes&subject=animal', undefined, false, { facts });
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    await page.mouse.move(2, 2);
    const node = page.locator('[data-family-tree-outline] [data-family-tree-node="74"]');
    await node.hover();
    const card = page.locator('[data-taxon-card]');
    await expect(card.locator('[data-taxon-card-description]')).toBeVisible();
    const fade = card.locator('[data-taxon-card-more]');
    await expect(fade).toBeVisible();
    // The fade belongs to the surface, not the pointer: it never takes a click.
    expect(await fade.evaluate((element) => getComputedStyle(element).pointerEvents)).toBe('none');
    const scroller = card.locator('[data-taxon-card-scroll]');
    await scroller.evaluate((element) => element.scrollTo({ top: element.scrollHeight }));
    await expect(fade).toHaveCount(0);
    const [view, text, source] = await Promise.all([
        scroller.boundingBox(),
        card.locator('[data-taxon-card-description] p').first().boundingBox(),
        card.locator('[data-taxon-card-description-source]').boundingBox()
    ]);
    expect(view && text && source).toBeTruthy();
    if (!view || !text || !source) return;
    for (const box of [text, source]) {
        expect(box.y).toBeGreaterThanOrEqual(view.y);
        expect(box.y + box.height).toBeLessThanOrEqual(view.y + view.height);
    }
    // The description is still clamped to three lines.
    const lines = await card.locator('[data-taxon-card-description] p').first().evaluate((element) =>
        Math.round(element.getBoundingClientRect().height / parseFloat(getComputedStyle(element).lineHeight)));
    expect(lines).toBeLessThanOrEqual(3);
});
