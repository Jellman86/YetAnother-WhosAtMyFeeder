import { describe, expect, it } from 'vitest';
import { elbowPath, fanLinkPath, fanPoint, layoutTree, treePoint, type LayoutInput } from './tree-layout';

const leaf = (id: string): LayoutInput<string> => ({ id, data: id, children: [] });
const branch = (id: string, children: LayoutInput<string>[]): LayoutInput<string> => ({ id, data: id, children });

describe('the family tree layout', () => {
    const tree = branch('Aves', [
        branch('Passeriformes', [branch('Prunellidae', [leaf('Dunnock'), leaf('Alpine accentor')]), leaf('Paridae')]),
        leaf('Columbiformes')
    ]);

    it('puts leaves one row apart in order and each rank in its own column', () => {
        const layout = layoutTree(tree);
        const at = (id: string) => layout.nodes.find((node) => node.id === id);
        expect(['Dunnock', 'Alpine accentor', 'Paridae', 'Columbiformes'].map((id) => at(id)?.row)).toEqual([0, 1, 2, 3]);
        expect(at('Dunnock')?.depth).toBe(3);
        expect(at('Columbiformes')?.depth).toBe(1);
        expect(layout.rows).toBe(4);
        expect(layout.depth).toBe(3);
    });

    it('centres a parent on its first and last visible child, and links every child to its parent', () => {
        const layout = layoutTree(tree);
        const at = (id: string) => layout.nodes.find((node) => node.id === id);
        expect(at('Prunellidae')?.row).toBe(0.5);
        expect(at('Passeriformes')?.row).toBe((0.5 + 2) / 2);
        expect(layout.links).toHaveLength(layout.nodes.length - 1);
        expect(layout.links).toContainEqual({ from: 'Prunellidae', to: 'Dunnock' });
        expect(at('Aves')?.parentId).toBeNull();
    });

    it('draws a lone root as one row, and places the tree and fan from the same rows and depths', () => {
        expect(layoutTree(leaf('Aves')).rows).toBe(1);
        expect(treePoint({ depth: 2, row: 3 }, 100, 20)).toEqual({ x: 216, y: 76 });
        const centre = fanPoint({ depth: 0, row: 0 }, 4, 80);
        expect(Math.hypot(centre.x, centre.y)).toBe(0);
        const outer = fanPoint({ depth: 2, row: 3 }, 4, 80);
        expect(Math.round(Math.hypot(outer.x, outer.y))).toBe(160);
    });
});

describe('the family tree as a cladogram', () => {
    const tree = branch('Aves', [
        branch('Passeriformes', [leaf('Corvidae'), leaf('Paridae'), leaf('Prunellidae')]),
        leaf('Columbiformes')
    ]);

    it('gives each node its level, the size of its set of siblings and its place in it', () => {
        const layout = layoutTree(tree);
        const at = (id: string) => layout.nodes.find((node) => node.id === id);
        expect(at('Aves')).toMatchObject({ setSize: 1, positionInSet: 1 });
        expect(at('Passeriformes')).toMatchObject({ setSize: 2, positionInSet: 1 });
        expect(at('Columbiformes')).toMatchObject({ setSize: 2, positionInSet: 2 });
        expect(at('Paridae')).toMatchObject({ setSize: 3, positionInSet: 2 });
    });

    it('joins a parent to a child with right angles: across to the junction, down, then across', () => {
        expect(elbowPath({ x: 10, y: 50 }, { x: 110, y: 90 }, 16)).toBe('M10,50H26V90H110');
        expect(elbowPath({ x: 0, y: 12.3456 }, { x: 80, y: 0.5 }, 8)).toBe('M0,12.35H8V0.5H80');
    });

    it('joins a fan parent to a child along the parent ring, then out along the child spoke', () => {
        const rows = 3;
        const sweep = Math.PI;
        const centre = { x: 100, y: 100 };
        // From the root the branch is one straight spoke.
        expect(fanLinkPath({ depth: 0, row: 1 }, { depth: 1, row: 0 }, rows, 40, sweep, centre)).toMatch(/^M100,100L/);
        const path = fanLinkPath({ depth: 1, row: 1 }, { depth: 2, row: 2 }, rows, 40, sweep, centre);
        const [, arc, , spoke] = path.match(/^M[^A]+A40,40 0 0 (\d) ([^L]+)L(.+)$/) ?? [];
        expect(arc).toBe('1');
        const [ax, ay] = spoke.split(',').map(Number);
        // The spoke ends on the child's ring at twice the parent's radius.
        expect(Math.round(Math.hypot(ax - centre.x, ay - centre.y))).toBe(80);
        // A child at the parent's own angle needs no arc.
        expect(fanLinkPath({ depth: 1, row: 1 }, { depth: 2, row: 1 }, rows, 40, sweep, centre)).not.toContain('A');
    });
});
