/**
 * Where each visible node of the family tree is drawn. Pure, so the tree, the fan and their tests
 * agree on one layout.
 *
 * The tree is laid out the way taxonomy trees usually are: each rank in its own column, leaves one
 * row apart in order, and a parent centred on its visible children. The fan is the same layout bent
 * round a circle, depth as the radius and row as the angle.
 */

export interface LayoutInput<T> {
    id: string;
    data: T;
    children: LayoutInput<T>[];
}

export interface PlacedNode<T> {
    id: string;
    data: T;
    depth: number;
    /** Row position: leaves are whole numbers, parents sit between their children. */
    row: number;
    parentId: string | null;
}

export interface Layout<T> {
    nodes: PlacedNode<T>[];
    links: { from: string; to: string }[];
    rows: number;
    depth: number;
}

export function layoutTree<T>(root: LayoutInput<T>): Layout<T> {
    const nodes: PlacedNode<T>[] = [];
    const links: { from: string; to: string }[] = [];
    let nextRow = 0;
    let maxDepth = 0;

    function place(node: LayoutInput<T>, depth: number, parentId: string | null): number {
        maxDepth = Math.max(maxDepth, depth);
        const placed: PlacedNode<T> = { id: node.id, data: node.data, depth, row: 0, parentId };
        nodes.push(placed);
        if (parentId !== null) links.push({ from: parentId, to: node.id });
        if (node.children.length === 0) {
            placed.row = nextRow;
            nextRow += 1;
        } else {
            const rows = node.children.map((child) => place(child, depth + 1, node.id));
            placed.row = (rows[0] + rows[rows.length - 1]) / 2;
        }
        return placed.row;
    }

    place(root, 0, null);
    return { nodes, links, rows: Math.max(1, nextRow), depth: maxDepth };
}

/** Pixel position on the horizontal tree: depth across, row down. */
export function treePoint(node: { depth: number; row: number }, columnWidth: number, rowHeight: number, inset = 16) {
    return { x: inset + node.depth * columnWidth, y: inset + node.row * rowHeight };
}

/**
 * Pixel position on the fan, relative to its centre: rows spread over `sweep` radians starting at
 * `start`, depth outward in rings. The root sits at the centre.
 */
export function fanPoint(
    node: { depth: number; row: number },
    rows: number,
    ringWidth: number,
    sweep = Math.PI * 1.6,
    start = -Math.PI / 2 - sweep / 2
) {
    const angle = start + (rows <= 1 ? 0.5 : node.row / (rows - 1)) * sweep;
    const radius = node.depth * ringWidth;
    return { x: radius * Math.cos(angle), y: radius * Math.sin(angle), angle };
}
