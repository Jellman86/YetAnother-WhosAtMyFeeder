/**
 * Where each visible node of the family tree is drawn. Pure, so the tree, the fan and their tests
 * agree on one layout.
 *
 * The tree is laid out as a cladogram: each rank in its own column, leaves one row apart in order,
 * a parent centred on its visible children, and branches that leave at right angles. The fan is the
 * same layout bent round a circle, depth as the radius and row as the angle, its branches running
 * along the parent's ring and then out along the child's spoke.
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
    /** How many siblings it has, itself included, and its place among them from 1. */
    setSize: number;
    positionInSet: number;
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

    function place(node: LayoutInput<T>, depth: number, parentId: string | null, setSize = 1, positionInSet = 1): number {
        maxDepth = Math.max(maxDepth, depth);
        const placed: PlacedNode<T> = { id: node.id, data: node.data, depth, row: 0, parentId, setSize, positionInSet };
        nodes.push(placed);
        if (parentId !== null) links.push({ from: parentId, to: node.id });
        if (node.children.length === 0) {
            placed.row = nextRow;
            nextRow += 1;
        } else {
            const rows = node.children.map((child, index) =>
                place(child, depth + 1, node.id, node.children.length, index + 1)
            );
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

interface Point {
    x: number;
    y: number;
}

// Two decimals is finer than a device pixel and keeps the drawn paths short and comparable.
const round = (value: number): number => Math.round(value * 100) / 100;

/**
 * A cladogram branch: across from the parent to its junction, along the junction to the child's
 * row, then across to the child. Siblings share the junction, so they read as one bracket.
 */
export function elbowPath(from: Point, to: Point, junction: number): string {
    return `M${round(from.x)},${round(from.y)}H${round(from.x + junction)}V${round(to.y)}H${round(to.x)}`;
}

/**
 * A fan branch: along the parent's ring to the child's angle, then out along the child's spoke.
 * From the root, which sits at the centre, it is a single spoke.
 */
export function fanLinkPath(
    parent: { depth: number; row: number },
    child: { depth: number; row: number },
    rows: number,
    ringWidth: number,
    sweep: number,
    centre: Point
): string {
    const from = fanPoint(parent, rows, ringWidth, sweep);
    const to = fanPoint(child, rows, ringWidth, sweep);
    const at = (point: Point) => `${round(centre.x + point.x)},${round(centre.y + point.y)}`;
    const radius = parent.depth * ringWidth;
    if (radius === 0 || Math.abs(to.angle - from.angle) < 1e-9) return `M${at(from)}L${at(to)}`;
    const corner = { x: radius * Math.cos(to.angle), y: radius * Math.sin(to.angle) };
    // SVG angles run clockwise, so a child at a larger angle is reached with the sweep flag set.
    const clockwise = to.angle > from.angle ? 1 : 0;
    return `M${at(from)}A${round(radius)},${round(radius)} 0 0 ${clockwise} ${at(corner)}L${at(to)}`;
}
