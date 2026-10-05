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

async function prepare(page: Page, path = '/browser-tests/family-tree.html', familyName = 'Accentors') {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.route((url) => url.pathname.startsWith('/api/'), async (route) => {
        const url = new URL(route.request().url());
        if (url.pathname === '/api/taxonomy/lineage') {
            if (url.searchParams.get('scientific_name') !== 'Prunella modularis') return route.fulfill({ status: 404, json: { detail: 'Species not in the catalogue' } });
            return route.fulfill({ json: { lineage: lineage.map((taxon) => (taxon.rank === 'family' ? { ...taxon, name: familyName } : taxon)) } });
        }
        const match = url.pathname.match(/^\/api\/taxonomy\/(\d+)\/children$/);
        if (match) return route.fulfill({ json: { parent_id: Number(match[1]), children: children[Number(match[1])] ?? [] } });
        throw new Error(`Unexpected family tree fixture request: ${url}`);
    });
    await page.goto(path);
    return { errors };
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
    await expect(dialog).toContainText('Animalia › Chordata › Aves');
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
    await expect(svg.getByRole('button', { name: '2 more' })).toHaveCount(3);
    await expect(svg.getByRole('button', { name: /Dunnock, Species, 324 captures here, this bird/ })).toHaveCount(1);
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

test('the fan and the outline show the same tree, the outline with disclosure buttons, and Escape closes', async ({ page }) => {
    await prepare(page);
    await page.getByRole('button', { name: 'Open the family tree' }).click();
    await page.locator('[data-family-tree-mode="fan"]').click();
    await expect(page.locator('[data-family-tree-svg="fan"] [data-family-tree-node="50"]')).toHaveCount(1);
    await page.locator('[data-family-tree-mode="outline"]').click();
    const outline = page.locator('[data-family-tree-outline]');
    await expect(outline.getByRole('button', { name: /Dunnock/ })).toHaveAttribute('aria-current', 'true');
    await expect(outline.getByRole('button', { name: /Passeriformes/ })).toHaveAttribute('aria-expanded', 'true');
    await outline.getByRole('button', { name: /Passeriformes/ }).click();
    await expect(outline.getByRole('button', { name: /Dunnock/ })).toHaveCount(0);
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
