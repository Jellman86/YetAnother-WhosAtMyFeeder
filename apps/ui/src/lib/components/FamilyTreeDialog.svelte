<script lang="ts">
    import { onMount, tick } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchTaxonChildren, type Taxon } from '../api/taxonomy';
    import { currentNamingStyle } from '../taxonomy/naming-style';
    import { byRank, formatScientificName, taxonNames, type NamePart } from '../taxonomy/nomenclature';
    import { elbowPath, fanLinkPath, fanPoint, layoutTree, type PlacedNode } from '../taxonomy/tree-layout';
    import { nodeMarker, visibleTree, type BranchState, type NodeMarker, type TreeItem } from '../taxonomy/tree-model';
    import { outlineGuides, treeKeyAction } from '../taxonomy/tree-navigation';
    import { portal } from '../utils/portal';
    import { isHoverPointer, isKeyboardFocus, TaxonPeek } from '../utils/taxon-peek.svelte';
    import TaxonCard from './TaxonCard.svelte';
    import TaxonMarker from './TaxonMarker.svelte';
    import TaxonNameText from './TaxonNameText.svelte';
    import { logger } from '../utils/logger';

    /**
     * The full family tree for one bird, drawn as a cladogram: each rank in its own column, named
     * at the top, and right-angled branches. The fan and an indented outline are other views of
     * the same data, and all three are one ARIA tree that the arrow keys move through.
     *
     * It opens on the path from the class down to the bird, every rank on it expanded. An open
     * branch shows the taxa on that path and those seen at this feeder, and sums the rest in one
     * node that opens them all. Branches load as they open, so the 11,000 birds never load at once.
     * It is a ranked classification as the sources publish it, not an evolutionary timeline.
     */
    interface Props {
        /** The bird's lineage, root first, as the lineage route returns it. */
        lineage: Taxon[];
        /** A Garden animal: what is seen here counts bird visits, so the tree does not claim it. */
        subject?: 'bird' | 'animal';
        onclose: () => void;
    }

    let { lineage, subject = 'bird', onclose }: Props = $props();

    type Mode = 'tree' | 'fan' | 'outline';
    const MODE_KEY = 'yawamf_family_tree_mode';
    let mode = $state<Mode>('tree');

    const style = $derived(currentNamingStyle());
    const principal = $derived(lineage.filter((taxon) => taxon.principal).sort(byRank));
    // The tree starts at the class: above it, a bird's lineage is one line (Animalia, Chordata),
    // shown as a ranked breadcrumb rather than as branches nobody needs to open.
    const rootIndex = $derived(Math.max(0, principal.findIndex((taxon) => taxon.rank === 'class')));
    const root = $derived(principal[rootIndex]);
    const above = $derived(principal.slice(0, rootIndex));
    const pathTaxa = $derived(principal.slice(rootIndex));
    const path = $derived(new Set(pathTaxa.map((taxon) => taxon.taxon_id)));
    const current = $derived(pathTaxa[pathTaxa.length - 1] ?? null);
    const currentNames = $derived(current ? taxonNames(current, style) : null);

    let branches = $state.raw<Map<number, BranchState>>(new Map());
    let expanded = $state.raw<Set<number>>(new Set());
    let failed = $state(false);
    // One card for the whole tree: a species' reference photo, any group's size and what was seen of it.
    const peek = new TaxonPeek();

    function setBranch(id: number, change: Partial<BranchState>): void {
        const next = new Map(branches);
        next.set(id, { children: null, showAll: false, loading: false, ...next.get(id), ...change });
        branches = next;
    }

    async function load(id: number): Promise<void> {
        if (branches.get(id)?.children || branches.get(id)?.loading) return;
        setBranch(id, { loading: true });
        try {
            const response = await fetchTaxonChildren(id);
            setBranch(id, { children: response.children, loading: false });
        } catch (error) {
            logger.warn('Family tree branch unavailable', { taxon: id, error });
            setBranch(id, { loading: false });
            failed = true;
        }
    }

    function toggle(taxon: Taxon): void {
        if (taxon.rank === 'species') return;
        const next = new Set(expanded);
        if (next.has(taxon.taxon_id)) {
            next.delete(taxon.taxon_id);
        } else {
            next.add(taxon.taxon_id);
            void load(taxon.taxon_id);
        }
        expanded = next;
    }

    const layout = $derived(
        root ? layoutTree(visibleTree({ root, branches, expanded, path, currentId: current?.taxon_id ?? null })) : null
    );
    const nodes = $derived(layout?.nodes ?? []);
    const byId = $derived(new Map(nodes.map((node) => [node.id, node])));
    // A node with branches leaving it; the rest are tips, labelled beyond their node.
    const branching = $derived(new Set((layout?.links ?? []).map((link) => link.from)));
    const guides = $derived(outlineGuides(nodes));
    const navigable = $derived(
        nodes.map((node) => ({
            id: node.id,
            parentId: node.parentId,
            depth: node.depth,
            expandable: node.data.kind === 'taxon' && node.data.expandable,
            expanded: node.data.kind === 'taxon' && node.data.expanded
        }))
    );

    // Geometry in rem, drawn at the root size, so the tree grows with the reader's text size.
    let unit = $state(16);
    const COLUMN = 14;
    const ROW = 3.25;
    const JUNCTION = 1;
    // Room left of the root for its label, above the first row for the rank headings, and right
    // of the deepest tips for theirs.
    const LEAD = 11;
    const HEADING = 2.5;
    const INSET = 1.5;
    const TIP = 16;
    const RING = 8;
    const FAN_LABEL = 13;

    const treeSize = $derived(
        layout
            ? { width: (LEAD + layout.depth * COLUMN + TIP) * unit, height: (HEADING + INSET * 2 + (layout.rows - 1) * ROW) * unit }
            : { width: 0, height: 0 }
    );
    const fanRadius = $derived(layout ? (layout.depth * RING + 2) * unit : 0);
    const fanCentre = $derived({ x: fanRadius + FAN_LABEL * unit, y: fanRadius });
    // A few open branches would splay round the whole circle; the fan widens as rows are added.
    const fanSweep = $derived(Math.min(Math.PI * 1.6, Math.max(Math.PI * 0.6, (layout?.rows ?? 1) * 0.3)));

    function position(node: { depth: number; row: number }): { x: number; y: number } {
        if (mode === 'fan' && layout) {
            const point = fanPoint(node, layout.rows, RING * unit, fanSweep);
            return { x: fanCentre.x + point.x, y: fanCentre.y + point.y };
        }
        return { x: (LEAD + node.depth * COLUMN) * unit, y: (HEADING + INSET + node.row * ROW) * unit };
    }

    function onPath(node: PlacedNode<TreeItem> | undefined): boolean {
        return node?.data.kind === 'taxon' && node.data.onPath;
    }

    // Branches off the path first, so the path is drawn over them where they share a junction.
    const links = $derived(
        [...(layout?.links ?? [])].sort((a, b) => Number(onPath(byId.get(a.to))) - Number(onPath(byId.get(b.to))))
    );

    function linkPath(fromId: string, toId: string): string {
        const from = byId.get(fromId);
        const to = byId.get(toId);
        if (!from || !to || !layout) return '';
        if (mode === 'fan') return fanLinkPath(from, to, layout.rows, RING * unit, fanSweep, fanCentre);
        return elbowPath(position(from), position(to), JUNCTION * unit);
    }

    // The rank each column holds, named once at its head instead of beside every node.
    const columnHeadings = $derived(
        Array.from({ length: (layout?.depth ?? -1) + 1 }, (_unused, depth) => {
            const ranks = [...new Set(nodes.filter((node) => node.depth === depth && node.data.kind === 'taxon').map((node) => (node.data.kind === 'taxon' ? node.data.taxon.rank : '')))];
            return { depth, label: ranks.map((rank) => $_(`taxonomy.rank.${rank}`, { default: rank })).join(' / ') };
        })
    );

    const showSeen = $derived(subject === 'bird');

    function markerFor(item: TreeItem): NodeMarker {
        return nodeMarker(item, showSeen);
    }

    function rankLabel(rank: string): string {
        return $_(`taxonomy.rank.${rank}`, { default: rank });
    }

    /** The same count on every node: a group's size and what was seen of it, a species' captures. */
    function countText(taxon: Taxon): string | null {
        if (subject === 'animal') return null;
        if (taxon.rank === 'species') {
            return (taxon.seen_count ?? 0) > 0
                ? $_('taxonomy.captures_here', { values: { count: taxon.seen_count }, default: '{count, plural, one {# capture here} other {# captures here}}' })
                : null;
        }
        if (taxon.species_count == null) return null;
        return $_('taxonomy.node_counts', {
            values: { total: taxon.species_count, seen: taxon.seen_species ?? 0 },
            default: '{total, plural, one {# species} other {# species}}, {seen} seen here'
        });
    }

    function moreLabel(hidden: number): string {
        return $_('taxonomy.more', { values: { count: hidden }, default: '{count} more' });
    }

    function ariaFor(item: TreeItem): string {
        if (item.kind === 'more') return moreLabel(item.hidden);
        const names = taxonNames(item.taxon, style);
        const parts = [names.primary.text, rankLabel(item.taxon.rank)];
        if (names.secondary) parts.splice(1, 0, names.secondary.text);
        const counts = countText(item.taxon);
        if (counts) parts.push(counts);
        if (item.current) {
            parts.push(subject === 'animal'
                ? $_('taxonomy.this_animal', { default: 'this animal' })
                : $_('taxonomy.this_bird', { default: 'this bird' }));
        }
        return parts.join(', ');
    }

    // Roving focus: one node of the tree takes Tab, and the arrow keys move it.
    let focusedId = $state<string | null>(null);
    const tabStop = $derived.by(() => {
        if (focusedId && byId.has(focusedId)) return focusedId;
        const bird = current ? `taxon:${current.taxon_id}` : null;
        if (bird && byId.has(bird)) return bird;
        return nodes[0]?.id ?? null;
    });

    let scroller = $state<HTMLElement | null>(null);
    let dialog = $state<HTMLElement | null>(null);

    async function focusNode(id: string): Promise<void> {
        focusedId = id;
        await tick();
        scroller?.querySelector<HTMLElement | SVGElement>(`[data-tree-id="${CSS.escape(id)}"]`)?.focus();
    }

    /** The card points at a node's marker, not at its whole click target, which reaches out over the label. */
    function cardAnchor(node: Element): Element {
        return node.querySelector('[data-tree-anchor]') ?? node;
    }

    function activate(node: PlacedNode<TreeItem>, element: Element, fromKeyboard: boolean): void {
        const item = node.data;
        if (item.kind === 'more') {
            const before = new Set(nodes.map((each) => each.id));
            setBranch(item.parentId, { showAll: true });
            // The "more" node is gone once the branch is open, so focus moves to the first taxon it held.
            if (fromKeyboard) {
                void tick().then(() => {
                    const first = nodes.find((each) => !before.has(each.id));
                    if (first) void focusNode(first.id);
                });
            }
        } else if (item.taxon.rank === 'species') {
            // A species has nothing beneath it to open, so selecting it shows its card.
            peek.toggle(item.taxon, item.current, cardAnchor(element));
        } else {
            peek.close();
            toggle(item.taxon);
        }
    }

    function onNodeKey(event: KeyboardEvent, node: PlacedNode<TreeItem>): void {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activate(node, event.currentTarget as Element, true);
            return;
        }
        const action = treeKeyAction(navigable, node.id, event.key);
        if (!action) return;
        event.preventDefault();
        if (action.kind === 'focus') {
            void focusNode(action.id);
            return;
        }
        const target = byId.get(action.id)?.data;
        if (target?.kind === 'taxon') toggle(target.taxon);
    }

    function peekHover(event: PointerEvent, item: TreeItem): void {
        if (item.kind === 'taxon' && isHoverPointer(event)) peek.hover(item.taxon, item.current, cardAnchor(event.currentTarget as Element));
    }

    function peekFocus(event: FocusEvent, node: PlacedNode<TreeItem>): void {
        focusedId = node.id;
        if (node.data.kind === 'taxon' && isKeyboardFocus(event.currentTarget)) peek.focus(node.data.taxon, node.data.current, cardAnchor(event.currentTarget as Element));
    }

    function centreOnBird(): void {
        if (!scroller || !layout || !current) return;
        const node = byId.get(`taxon:${current.taxon_id}`);
        if (!node) return;
        const point = position(node);
        scroller.scrollTo({ left: Math.max(0, point.x - scroller.clientWidth / 2), top: Math.max(0, point.y - scroller.clientHeight / 2) });
    }

    function setMode(next: Mode): void {
        peek.close();
        mode = next;
        try {
            localStorage.setItem(MODE_KEY, next);
        } catch {
            // A private window keeps the choice for this visit only.
        }
        void tick().then(centreOnBird);
    }

    function onKey(event: KeyboardEvent): void {
        if (event.key === 'Escape') {
            event.stopPropagation();
            // An open card closes first; the tree stays open.
            if (peek.anchor) peek.close();
            else onclose();
        }
    }

    function measureUnit(): void {
        unit = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
    }

    onMount(() => {
        measureUnit();
        try {
            const saved = localStorage.getItem(MODE_KEY);
            if (saved === 'tree' || saved === 'fan' || saved === 'outline') mode = saved;
            // A phone has no room for a sideways tree: until the reader picks a layout, it opens as the outline.
            else if (window.matchMedia('(max-width: 639px)').matches) mode = 'outline';
        } catch {
            // Default view.
        }
        expanded = new Set(pathTaxa.filter((taxon) => taxon.rank !== 'species').map((taxon) => taxon.taxon_id));
        void Promise.all([...expanded].map((id) => load(id))).then(() => tick().then(centreOnBird));
        dialog?.focus();
        window.addEventListener('keydown', onKey, true);
        // The root size follows the window width, so the drawing is re-measured with it.
        window.addEventListener('resize', measureUnit);
        return () => {
            window.removeEventListener('keydown', onKey, true);
            window.removeEventListener('resize', measureUnit);
        };
    });

    const MODES: Mode[] = ['tree', 'fan', 'outline'];
    function modeLabel(value: Mode): string {
        if (value === 'tree') return $_('taxonomy.layout_tree', { default: 'Tree' });
        if (value === 'fan') return $_('taxonomy.layout_fan', { default: 'Fan' });
        return $_('taxonomy.layout_outline', { default: 'Outline' });
    }

    const LEGEND_MARKERS: Record<'current' | 'path' | 'seen' | 'closed', NodeMarker> = {
        current: { tone: 'current', closed: false },
        path: { tone: 'path', closed: false },
        seen: { tone: 'seen', closed: false },
        closed: { tone: 'plain', closed: true }
    };
</script>

{#snippet htmlMarker(marker: NodeMarker)}
    <svg class="h-4 w-4 shrink-0 overflow-visible" viewBox="-8 -8 16 16" aria-hidden="true"><TaxonMarker {marker} unit={16} /></svg>
{/snippet}

<div
    use:portal
    class="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/70 p-0 sm:p-4"
    role="presentation"
    onclick={(event) => {
        if (event.target === event.currentTarget) onclose();
    }}
>
    <div
        bind:this={dialog}
        class="flex h-[100dvh] w-full max-w-6xl flex-col overflow-hidden bg-surface sm:h-[90dvh] sm:rounded-2xl sm:border sm:border-line"
        role="dialog"
        aria-modal="true"
        aria-labelledby="family-tree-title"
        tabindex="-1"
        data-family-tree
    >
        <header class="flex flex-wrap items-start justify-between gap-3 border-b border-line-soft px-4 py-3 sm:px-6">
            <div class="min-w-0 space-y-1">
                <h2 id="family-tree-title" class="font-display text-xl font-bold text-slate-900 dark:text-white">
                    {$_('taxonomy.title', { values: { name: currentNames?.primary.text ?? '' }, default: 'Family tree of {name}' })}
                </h2>
                {#if currentNames?.secondary}
                    <p class="text-sm text-slate-600 dark:text-slate-300" data-family-tree-subtitle><TaxonNameText name={currentNames.secondary} /></p>
                {/if}
                {#if above.length > 0}
                    <ol class="flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs text-slate-600 dark:text-slate-300" aria-label={$_('taxonomy.breadcrumb_label', { default: 'Ranks above the class' })} data-family-tree-breadcrumb>
                        {#each above as taxon, index (taxon.taxon_id)}
                            <li class="flex items-baseline gap-1.5">
                                {#if index > 0}<span class="text-slate-400 dark:text-slate-500" aria-hidden="true">›</span>{/if}
                                <span class="taxon-rank">{rankLabel(taxon.rank)}</span>
                                <span>{formatScientificName(taxon.rank, taxon.scientific_name).map((part) => part.text).join('')}</span>
                            </li>
                        {/each}
                    </ol>
                {/if}
            </div>
            <div class="flex flex-wrap items-center gap-2">
                <div class="inline-flex gap-1 rounded-xl bg-surface-raised p-1" role="group" aria-label={$_('taxonomy.layouts', { default: 'Layout' })}>
                    {#each MODES as value (value)}
                        <button
                            type="button"
                            class="tab-button px-3 py-2 {mode === value ? 'tab-button-active' : 'tab-button-inactive'}"
                            aria-pressed={mode === value}
                            onclick={() => setMode(value)}
                            data-family-tree-mode={value}
                        >{modeLabel(value)}</button>
                    {/each}
                </div>
                <button type="button" class="btn btn-ghost min-h-11 px-4" onclick={onclose} data-family-tree-close>
                    {$_('common.close', { default: 'Close' })}
                </button>
            </div>
        </header>

        <div class="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 pt-3 text-2xs text-slate-600 dark:text-slate-300 sm:px-6" data-family-tree-legend>
            <span class="inline-flex items-center gap-1.5">{@render htmlMarker(LEGEND_MARKERS.current)}{subject === 'animal'
                ? $_('taxonomy.legend_this_animal', { default: 'This animal' })
                : $_('taxonomy.legend_this_bird', { default: 'This bird' })}</span>
            <span class="inline-flex items-center gap-1.5">{@render htmlMarker(LEGEND_MARKERS.path)}{subject === 'animal'
                ? $_('taxonomy.legend_path_animal', { default: 'Path to this animal' })
                : $_('taxonomy.legend_path', { default: 'Path to this bird' })}</span>
            {#if showSeen}
                <span class="inline-flex items-center gap-1.5">{@render htmlMarker(LEGEND_MARKERS.seen)}{$_('taxonomy.legend_seen', { default: 'Seen at this feeder' })}</span>
            {/if}
            <span class="inline-flex items-center gap-1.5">{@render htmlMarker(LEGEND_MARKERS.closed)}{$_('taxonomy.legend_closed', { default: 'Closed group, select to open' })}</span>
            <span class="text-slate-500 dark:text-slate-400">{$_('taxonomy.legend_open', { default: 'Select a group to open or close it' })}</span>
            <span class="hidden text-slate-500 dark:text-slate-400 sm:inline">{$_('taxonomy.legend_keys', { default: 'Arrow keys move through the tree.' })}</span>
        </div>

        <div bind:this={scroller} class="relative min-h-0 flex-1 overflow-auto px-2 py-2 sm:px-4" data-family-tree-canvas>
            {#if !layout}
                <p class="p-6 text-sm text-slate-500 dark:text-slate-400">{$_('taxonomy.loading', { default: 'Loading the family tree' })}</p>
            {:else if mode === 'outline'}
                <div class="py-2" role="tree" aria-label={$_('taxonomy.outline_label', { default: 'Family tree outline' })} data-family-tree-outline>
                    {#each nodes as node (node.id)}
                        {@const item = node.data}
                        {@const names = item.kind === 'taxon' ? taxonNames(item.taxon, style) : null}
                        {@const counts = item.kind === 'taxon' ? countText(item.taxon) : null}
                        <div
                            class="flex min-h-11 cursor-pointer items-stretch rounded-lg pr-2 hover:bg-surface-raised focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500"
                            role="treeitem"
                            tabindex={tabStop === node.id ? 0 : -1}
                            aria-level={node.depth + 1}
                            aria-setsize={node.setSize}
                            aria-posinset={node.positionInSet}
                            aria-expanded={item.kind === 'taxon' && item.expandable ? item.expanded : undefined}
                            aria-current={item.kind === 'taxon' && item.current ? 'true' : undefined}
                            aria-selected={item.kind === 'taxon' && item.current}
                            aria-label={ariaFor(item)}
                            onclick={(event) => activate(node, event.currentTarget, false)}
                            onkeydown={(event) => onNodeKey(event, node)}
                            onpointerenter={(event) => peekHover(event, item)}
                            onpointerleave={() => peek.leave()}
                            onfocus={(event) => peekFocus(event, node)}
                            onblur={() => peek.leave()}
                            data-taxon-peek-trigger
                            data-tree-id={node.id}
                            data-family-tree-node={item.kind === 'taxon' ? item.taxon.taxon_id : `more:${item.parentId}`}
                        >
                            {#each guides.get(node.id) ?? [] as guide, index (index)}
                                <span class="relative w-5 shrink-0" aria-hidden="true">
                                    {#if guide === 'line' || guide === 'tee'}
                                        <span class="absolute inset-y-0 left-1/2 border-l border-slate-300 dark:border-slate-600"></span>
                                    {:else if guide === 'last'}
                                        <span class="absolute left-1/2 top-0 h-1/2 border-l border-slate-300 dark:border-slate-600"></span>
                                    {/if}
                                    {#if guide === 'tee' || guide === 'last'}
                                        <span class="absolute -right-2 left-1/2 top-1/2 border-t border-slate-300 dark:border-slate-600"></span>
                                    {/if}
                                </span>
                            {/each}
                            <span class="relative flex w-5 shrink-0 items-center justify-center" aria-hidden="true">
                                {#if branching.has(node.id)}
                                    <span class="absolute bottom-0 left-1/2 top-1/2 border-l border-slate-300 dark:border-slate-600"></span>
                                {/if}
                                <span class="relative">{@render htmlMarker(markerFor(item))}</span>
                            </span>
                            {#if item.kind === 'more'}
                                <span class="flex items-center pl-2 text-sm text-slate-500 dark:text-slate-400">{moreLabel(item.hidden)}</span>
                            {:else if names}
                                <span class="flex min-w-0 flex-1 flex-col justify-center py-1 pl-2">
                                    <span class="flex min-w-0 items-baseline gap-2">
                                        <TaxonNameText
                                            name={names.primary}
                                            class="truncate text-sm leading-5 {item.current ? 'font-bold text-slate-900 dark:text-white' : 'font-medium text-slate-800 dark:text-slate-100'}"
                                        />
                                        <span class="taxon-rank shrink-0">{rankLabel(item.taxon.rank)}</span>
                                    </span>
                                    {#if names.secondary || counts}
                                        <span class="truncate text-2xs leading-4 text-slate-500 dark:text-slate-400">
                                            {#if names.secondary}<TaxonNameText name={names.secondary} />{/if}{#if names.secondary && counts}<span aria-hidden="true">{' · '}</span>{/if}{#if counts}<span class="tabular-nums" data-family-tree-counts>{counts}</span>{/if}
                                        </span>
                                    {/if}
                                </span>
                            {/if}
                        </div>
                    {/each}
                </div>
            {:else}
                {@const size = mode === 'fan' ? { width: fanCentre.x * 2, height: fanRadius * 2 } : treeSize}
                <div class="flex min-h-full min-w-full">
                    <svg
                        width={size.width}
                        height={size.height}
                        class="block shrink-0 {mode === 'fan' ? 'm-auto' : 'mx-auto'}"
                        role="tree"
                        aria-label={$_('taxonomy.tree_label', { default: 'Classification tree' })}
                        data-family-tree-svg={mode}
                    >
                        {#snippet svgName(parts: NamePart[])}{#each parts as part, index (index)}<tspan font-style={part.italic ? 'italic' : 'normal'}>{part.text}</tspan>{/each}{/snippet}
                        {#if mode === 'tree'}
                            {#each columnHeadings as heading (heading.depth)}
                                <text
                                    x={position({ depth: heading.depth, row: 0 }).x}
                                    y={INSET * unit}
                                    text-anchor="middle"
                                    class="fill-slate-500 text-3xs font-semibold uppercase tracking-widest dark:fill-slate-400"
                                    aria-hidden="true"
                                    data-family-tree-rank-heading
                                >{heading.label}</text>
                            {/each}
                        {/if}
                        {#each links as link (link.to)}
                            {@const strong = onPath(byId.get(link.to))}
                            <path
                                d={linkPath(link.from, link.to)}
                                fill="none"
                                class={strong ? 'stroke-slate-700 dark:stroke-slate-200' : 'stroke-slate-300 dark:stroke-slate-600'}
                                stroke-width={strong ? 2 : 1}
                                stroke-linejoin="miter"
                                aria-hidden="true"
                            />
                        {/each}
                        {#each nodes as node (node.id)}
                            {@const item = node.data}
                            {@const point = position(node)}
                            {@const names = item.kind === 'taxon' ? taxonNames(item.taxon, style) : null}
                            {@const counts = item.kind === 'taxon' ? countText(item.taxon) : null}
                            {@const before = mode === 'fan' ? point.x < fanCentre.x - 1 : branching.has(node.id)}
                            {@const labelX = (before ? -0.75 : 0.75) * unit}
                            <g
                                transform="translate({point.x},{point.y})"
                                role="treeitem"
                                tabindex={tabStop === node.id ? 0 : -1}
                                aria-level={node.depth + 1}
                                aria-setsize={node.setSize}
                                aria-posinset={node.positionInSet}
                                aria-expanded={item.kind === 'taxon' && item.expandable ? item.expanded : undefined}
                                aria-current={item.kind === 'taxon' && item.current ? 'true' : undefined}
                                aria-selected={item.kind === 'taxon' && item.current}
                                aria-label={ariaFor(item)}
                                class="tree-node cursor-pointer focus:outline-none"
                                onclick={(event) => activate(node, event.currentTarget, false)}
                                onkeydown={(event) => onNodeKey(event, node)}
                                onpointerenter={(event) => peekHover(event, item)}
                                onpointerleave={() => peek.leave()}
                                onfocus={(event) => peekFocus(event, node)}
                                onblur={() => peek.leave()}
                                data-taxon-peek-trigger
                                data-tree-id={node.id}
                                data-family-tree-node={item.kind === 'taxon' ? item.taxon.taxon_id : `more:${item.parentId}`}
                            >
                                {#if mode === 'tree'}
                                    <!-- The whole row is the target, label and gap included, one 44px row tall. -->
                                    <rect x={(before ? -12.5 : -0.9) * unit} y={(-ROW / 2) * unit} width={13.4 * unit} height={ROW * unit} class="fill-transparent" data-family-tree-hit />
                                {/if}
                                <circle r={0.875 * unit} class="focus-ring fill-transparent stroke-brand-500" stroke-width="2" data-tree-anchor />
                                <TaxonMarker marker={markerFor(item)} {unit} />
                                {#if item.kind === 'more'}
                                    <text x={labelX} y={0.3 * unit} text-anchor={before ? 'end' : 'start'} class="tree-label fill-slate-500 text-xs font-medium dark:fill-slate-400">{moreLabel(item.hidden)}</text>
                                {:else if names}
                                    <!-- The name above the branch, the second name or rank and the counts below it. -->
                                    <text
                                        x={labelX}
                                        y={-0.4 * unit}
                                        text-anchor={before ? 'end' : 'start'}
                                        class="tree-label text-xs {item.current ? 'font-bold fill-slate-900 dark:fill-white' : 'font-semibold fill-slate-800 dark:fill-slate-100'}"
                                        data-family-tree-label
                                    >{@render svgName(names.primary.parts)}</text>
                                    <text
                                        x={labelX}
                                        y={1 * unit}
                                        text-anchor={before ? 'end' : 'start'}
                                        class="tree-label fill-slate-500 text-3xs dark:fill-slate-400"
                                    >{#if mode === 'fan'}<tspan class="font-semibold uppercase tracking-widest">{rankLabel(item.taxon.rank)}</tspan>{:else if names.secondary}{@render svgName(names.secondary.parts)}{/if}{#if counts}{#if mode === 'fan' || names.secondary}<tspan>{' · '}</tspan>{/if}<tspan class="tabular-nums {item.kind === 'taxon' && showSeen && (item.taxon.seen_species ?? 0) > 0 ? 'fill-emerald-700 dark:fill-emerald-300' : ''}">{counts}</tspan>{/if}</text>
                                {/if}
                            </g>
                        {/each}
                    </svg>
                </div>
            {/if}
        </div>

        <footer class="border-t border-line-soft px-4 py-2 text-2xs text-slate-500 dark:text-slate-400 sm:px-6">
            {#if failed}
                <span class="mr-2 font-semibold text-amber-700 dark:text-amber-300">{$_('taxonomy.branch_failed', { default: 'Part of the tree could not load. Open it again to retry.' })}</span>
            {/if}
            {subject === 'animal'
                ? $_('taxonomy.source_note_animal', { default: 'Classification from the SpeciesNet taxonomy for Garden animals. It shows how species are grouped, not when they diverged.' })
                : $_('taxonomy.source_note', { default: 'Classification from the IOC World Bird List for birds and the Catalogue of Life above them. It shows how species are grouped, not when they diverged.' })}
        </footer>
    </div>
</div>

<TaxonCard {peek} {subject} />

<style>
    /* A halo in the canvas colour, so a branch passing behind a label never strikes it through. */
    .tree-label {
        paint-order: stroke;
        stroke: rgb(var(--surface));
        stroke-width: 4px;
        stroke-linejoin: round;
    }
    .tree-node .focus-ring {
        opacity: 0;
    }
    .tree-node:focus-visible .focus-ring {
        opacity: 1;
    }
</style>
