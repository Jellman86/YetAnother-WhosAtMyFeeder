/**
 * Keyboard movement and connector lines for the family tree, as the WAI-ARIA tree pattern
 * describes them. Pure, so the tree, the fan and the outline move the same way.
 *
 * Nodes arrive in reading order: each parent before its children, children in source order.
 */

export interface NavigableNode {
    id: string;
    parentId: string | null;
    depth: number;
    expandable: boolean;
    expanded: boolean;
}

export type TreeKeyAction = { kind: 'focus' | 'expand' | 'collapse'; id: string } | null;

/**
 * What a key does from the focused node. Up and Down step through the visible nodes, Home and End
 * jump to the ends, Right opens a closed group or steps into an open one, and Left closes an open
 * group or steps out to the parent.
 */
export function treeKeyAction(nodes: readonly NavigableNode[], focusedId: string, key: string): TreeKeyAction {
    const index = nodes.findIndex((node) => node.id === focusedId);
    if (index < 0) return null;
    const node = nodes[index];
    const focus = (target: NavigableNode | undefined): TreeKeyAction => (target ? { kind: 'focus', id: target.id } : null);

    switch (key) {
        case 'ArrowDown':
            return focus(nodes[index + 1]);
        case 'ArrowUp':
            return focus(nodes[index - 1]);
        case 'Home':
            return focus(nodes[0]);
        case 'End':
            return focus(nodes[nodes.length - 1]);
        case 'ArrowRight':
            if (node.expandable && !node.expanded) return { kind: 'expand', id: node.id };
            return nodes[index + 1]?.parentId === node.id ? focus(nodes[index + 1]) : null;
        case 'ArrowLeft':
            if (node.expandable && node.expanded) return { kind: 'collapse', id: node.id };
            return focus(nodes.find((candidate) => candidate.id === node.parentId));
        default:
            return null;
    }
}

/**
 * The connector in each indent column of an outline row. `line` carries an ancestor's bracket
 * past this row, `tee` and `last` join the row to its parent with or without later siblings.
 */
export type OutlineGuide = 'none' | 'line' | 'tee' | 'last';

export function outlineGuides(nodes: readonly Pick<NavigableNode, 'id' | 'parentId' | 'depth'>[]): Map<string, OutlineGuide[]> {
    const lastChild = new Map<string | null, string>();
    const parentOf = new Map<string, string | null>();
    for (const node of nodes) {
        lastChild.set(node.parentId, node.id);
        parentOf.set(node.id, node.parentId);
    }
    const hasLaterSibling = (id: string): boolean => lastChild.get(parentOf.get(id) ?? null) !== id;

    const guides = new Map<string, OutlineGuide[]>();
    for (const node of nodes) {
        const columns: OutlineGuide[] = [];
        if (node.parentId !== null) columns.unshift(hasLaterSibling(node.id) ? 'tee' : 'last');
        // Each ancestor below the root keeps its bracket open while it has siblings still to come.
        let ancestor = node.parentId;
        while (ancestor !== null && parentOf.get(ancestor) !== null && parentOf.has(ancestor)) {
            columns.unshift(hasLaterSibling(ancestor) ? 'line' : 'none');
            ancestor = parentOf.get(ancestor) ?? null;
        }
        guides.set(node.id, columns);
    }
    return guides;
}
