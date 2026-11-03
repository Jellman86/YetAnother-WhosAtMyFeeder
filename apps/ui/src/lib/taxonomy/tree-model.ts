import type { Taxon } from '../api/taxonomy';
import type { LayoutInput } from './tree-layout';

/**
 * Which part of the classification the family tree shows. A whole order can hold hundreds of
 * families, so an open branch shows only the taxa on the path to the bird being viewed and the
 * ones seen at this feeder, with the rest summed in one "more" node until asked for.
 */

export type TreeItem =
    | {
          kind: 'taxon';
          taxon: Taxon;
          onPath: boolean;
          current: boolean;
          /** It has (or may have) taxa beneath it to open. */
          expandable: boolean;
          expanded: boolean;
          loading: boolean;
      }
    | { kind: 'more'; parentId: number; hidden: number };

export interface BranchState {
    /** Null until the branch has been read. */
    children: Taxon[] | null;
    showAll: boolean;
    loading: boolean;
}

export interface TreeView {
    root: Taxon;
    branches: ReadonlyMap<number, BranchState>;
    expanded: ReadonlySet<number>;
    /** The taxa from the root down to the bird being viewed. */
    path: ReadonlySet<number>;
    currentId: number | null;
}

function isSeen(taxon: Taxon): boolean {
    return (taxon.seen_species ?? 0) > 0;
}

/** The visible tree, in the shape the layout takes. */
export function visibleTree(view: TreeView): LayoutInput<TreeItem> {
    function build(taxon: Taxon): LayoutInput<TreeItem> {
        const branch = view.branches.get(taxon.taxon_id);
        const expanded = view.expanded.has(taxon.taxon_id);
        const item: TreeItem = {
            kind: 'taxon',
            taxon,
            onPath: view.path.has(taxon.taxon_id),
            current: taxon.taxon_id === view.currentId,
            expandable: taxon.rank !== 'species',
            expanded,
            loading: Boolean(branch?.loading)
        };
        const children: LayoutInput<TreeItem>[] = [];
        if (expanded && branch?.children) {
            const shown = branch.children.filter(
                (child) => branch.showAll || view.path.has(child.taxon_id) || isSeen(child)
            );
            for (const child of shown) children.push(build(child));
            const hidden = branch.children.length - shown.length;
            if (hidden > 0) {
                children.push({
                    id: `more:${taxon.taxon_id}`,
                    data: { kind: 'more', parentId: taxon.taxon_id, hidden },
                    children: []
                });
            }
        }
        return { id: `taxon:${taxon.taxon_id}`, data: item, children };
    }
    return build(view.root);
}

/**
 * How a node is drawn, the same in the tree, the fan, the outline and the legend. Tone says where
 * it stands (this bird, on its path, seen here, anything else); `closed` adds a plus for a group
 * that has more inside, so neither depends on colour alone.
 */
type MarkerTone = 'current' | 'path' | 'seen' | 'plain' | 'more';

export interface NodeMarker {
    tone: MarkerTone;
    closed: boolean;
}

export function nodeMarker(item: TreeItem, showSeen: boolean): NodeMarker {
    if (item.kind === 'more') return { tone: 'more', closed: false };
    const closed = item.expandable && !item.expanded;
    if (item.current) return { tone: 'current', closed };
    if (item.onPath) return { tone: 'path', closed };
    if (showSeen && isSeen(item.taxon)) return { tone: 'seen', closed };
    return { tone: 'plain', closed };
}
