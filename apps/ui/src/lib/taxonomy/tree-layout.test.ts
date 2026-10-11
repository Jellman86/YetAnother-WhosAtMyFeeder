import { describe, expect, it } from 'vitest';
import { fanPoint, layoutTree, treePoint, type LayoutInput } from './tree-layout';

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
