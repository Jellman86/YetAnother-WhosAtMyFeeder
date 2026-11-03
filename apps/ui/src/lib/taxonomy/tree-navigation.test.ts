import { describe, expect, it } from 'vitest';
import { outlineGuides, treeKeyAction, type NavigableNode } from './tree-navigation';

// Aves > (Passeriformes > (Corvidae, Prunellidae > Prunella), Columbiformes [closed])
const nodes: NavigableNode[] = [
    { id: 'aves', parentId: null, depth: 0, expandable: true, expanded: true },
    { id: 'passeriformes', parentId: 'aves', depth: 1, expandable: true, expanded: true },
    { id: 'corvidae', parentId: 'passeriformes', depth: 2, expandable: true, expanded: false },
    { id: 'prunellidae', parentId: 'passeriformes', depth: 2, expandable: true, expanded: true },
    { id: 'prunella', parentId: 'prunellidae', depth: 3, expandable: true, expanded: false },
    { id: 'columbiformes', parentId: 'aves', depth: 1, expandable: true, expanded: false },
    { id: 'more', parentId: 'aves', depth: 1, expandable: false, expanded: false }
];

describe('moving through the family tree from the keyboard', () => {
    it('moves down and up through the visible nodes in reading order, stopping at the ends', () => {
        expect(treeKeyAction(nodes, 'passeriformes', 'ArrowDown')).toEqual({ kind: 'focus', id: 'corvidae' });
        expect(treeKeyAction(nodes, 'prunella', 'ArrowDown')).toEqual({ kind: 'focus', id: 'columbiformes' });
        expect(treeKeyAction(nodes, 'corvidae', 'ArrowUp')).toEqual({ kind: 'focus', id: 'passeriformes' });
        expect(treeKeyAction(nodes, 'aves', 'ArrowUp')).toBeNull();
        expect(treeKeyAction(nodes, 'more', 'ArrowDown')).toBeNull();
    });

    it('jumps to the first and last node with Home and End', () => {
        expect(treeKeyAction(nodes, 'prunella', 'Home')).toEqual({ kind: 'focus', id: 'aves' });
        expect(treeKeyAction(nodes, 'aves', 'End')).toEqual({ kind: 'focus', id: 'more' });
    });

    it('opens a closed group with the right arrow, then steps into its first child', () => {
        expect(treeKeyAction(nodes, 'columbiformes', 'ArrowRight')).toEqual({ kind: 'expand', id: 'columbiformes' });
        expect(treeKeyAction(nodes, 'prunellidae', 'ArrowRight')).toEqual({ kind: 'focus', id: 'prunella' });
        // An open group whose children have not arrived yet has nowhere to go.
        const loading = nodes.map((node) => (node.id === 'prunella' ? { ...node, expanded: true } : node));
        expect(treeKeyAction(loading, 'prunella', 'ArrowRight')).toBeNull();
        expect(treeKeyAction(nodes, 'more', 'ArrowRight')).toBeNull();
    });

    it('closes an open group with the left arrow, otherwise steps out to the parent', () => {
        expect(treeKeyAction(nodes, 'prunellidae', 'ArrowLeft')).toEqual({ kind: 'collapse', id: 'prunellidae' });
        expect(treeKeyAction(nodes, 'corvidae', 'ArrowLeft')).toEqual({ kind: 'focus', id: 'passeriformes' });
        expect(treeKeyAction(nodes, 'more', 'ArrowLeft')).toEqual({ kind: 'focus', id: 'aves' });
        expect(treeKeyAction([{ ...nodes[0], expanded: false }], 'aves', 'ArrowLeft')).toBeNull();
    });

    it('ignores other keys and a node that is no longer shown', () => {
        expect(treeKeyAction(nodes, 'aves', 'a')).toBeNull();
        expect(treeKeyAction(nodes, 'gone', 'ArrowDown')).toBeNull();
    });
});

describe('the outline connector lines', () => {
    it('draws a tee for a node with later siblings, a corner for the last, and carries open lines down', () => {
        const guides = outlineGuides(nodes);
        expect(guides.get('aves')).toEqual([]);
        expect(guides.get('passeriformes')).toEqual(['tee']);
        expect(guides.get('corvidae')).toEqual(['line', 'tee']);
        expect(guides.get('prunellidae')).toEqual(['line', 'last']);
        expect(guides.get('prunella')).toEqual(['line', 'none', 'last']);
        expect(guides.get('columbiformes')).toEqual(['tee']);
        expect(guides.get('more')).toEqual(['last']);
    });
});
