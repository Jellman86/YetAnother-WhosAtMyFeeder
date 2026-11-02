import { describe, expect, it } from 'vitest';
import type { Taxon } from '../api/taxonomy';
import { layoutTree } from './tree-layout';
import { nodeMarker, visibleTree, type BranchState, type TreeItem } from './tree-model';

const taxon = (taxon_id: number, scientific_name: string, rank: string, seen_species = 0, name: string | null = null): Taxon => ({
    taxon_id, scientific_name, rank, name, principal: true, seen_species, seen_count: seen_species * 10
});

const aves = taxon(1, 'Aves', 'class', 2, 'Birds');
const passeriformes = taxon(2, 'Passeriformes', 'order', 2);
const piciformes = taxon(3, 'Piciformes', 'order');
const strigiformes = taxon(4, 'Strigiformes', 'order');
const prunellidae = taxon(5, 'Prunellidae', 'family', 1, 'Accentors');
const paridae = taxon(6, 'Paridae', 'family', 1);
const corvidae = taxon(7, 'Corvidae', 'family');

function view(overrides: { expanded?: number[]; showAll?: number[] } = {}) {
    const showAll = new Set(overrides.showAll ?? []);
    const branches = new Map<number, BranchState>([
        [1, { children: [passeriformes, piciformes, strigiformes], showAll: showAll.has(1), loading: false }],
        [2, { children: [corvidae, paridae, prunellidae], showAll: showAll.has(2), loading: false }]
    ]);
    return {
        root: aves,
        branches,
        expanded: new Set(overrides.expanded ?? [1, 2]),
        path: new Set([1, 2, 5]),
        currentId: 5
    };
}

const ids = (tree: ReturnType<typeof visibleTree>) =>
    layoutTree(tree).nodes.map((node) => node.id);

describe('the family tree model', () => {
    it('shows the path and what was seen here, and sums the rest into one more node', () => {
        expect(ids(visibleTree(view()))).toEqual([
            'taxon:1', 'taxon:2', 'taxon:6', 'taxon:5', 'more:2', 'more:1'
        ]);
        const more = layoutTree(visibleTree(view())).nodes.find((node) => node.id === 'more:1')?.data as TreeItem;
        expect(more).toEqual({ kind: 'more', parentId: 1, hidden: 2 });
    });

    it('shows every child of a branch once it is asked for, in the source order', () => {
        expect(ids(visibleTree(view({ showAll: [2] })))).toEqual([
            'taxon:1', 'taxon:2', 'taxon:7', 'taxon:6', 'taxon:5', 'more:1'
        ]);
    });

    it('hides a closed branch entirely, and marks the path and the current bird', () => {
        expect(ids(visibleTree(view({ expanded: [1] })))).toEqual(['taxon:1', 'taxon:2', 'more:1']);
        const nodes = layoutTree(visibleTree(view())).nodes;
        const accentors = nodes.find((node) => node.id === 'taxon:5')?.data;
        expect(accentors).toMatchObject({ kind: 'taxon', onPath: true, current: true, expandable: true });
    });

    it('marks the bird, its path, what was seen here and closed groups by shape as well as tone', () => {
        const item = (overrides: Partial<Extract<TreeItem, { kind: 'taxon' }>>): TreeItem => ({
            kind: 'taxon', taxon: paridae, onPath: false, current: false, expandable: true, expanded: false, loading: false, ...overrides
        });
        expect(nodeMarker(item({ current: true, onPath: true, expanded: true }), true)).toEqual({ tone: 'current', closed: false });
        expect(nodeMarker(item({ onPath: true, expanded: true }), true)).toEqual({ tone: 'path', closed: false });
        expect(nodeMarker(item({}), true)).toEqual({ tone: 'seen', closed: true });
        // A Garden tree counts no bird visits, so nothing is marked as seen there.
        expect(nodeMarker(item({}), false)).toEqual({ tone: 'plain', closed: true });
        expect(nodeMarker(item({ taxon: corvidae, expanded: true }), true)).toEqual({ tone: 'plain', closed: false });
        expect(nodeMarker(item({ taxon: { ...corvidae, rank: 'species' }, expandable: false }), true)).toEqual({ tone: 'plain', closed: false });
        expect(nodeMarker({ kind: 'more', parentId: 1, hidden: 3 }, true)).toEqual({ tone: 'more', closed: false });
    });
});
