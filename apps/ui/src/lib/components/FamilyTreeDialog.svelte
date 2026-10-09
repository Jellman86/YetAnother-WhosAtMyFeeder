<script lang="ts">
    import { onMount, tick } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { fetchTaxonChildren, type Taxon } from '../api/taxonomy';
    import { fanPoint, layoutTree, treePoint, type PlacedNode } from '../taxonomy/tree-layout';
    import { isSeen, taxonLabel, visibleTree, type BranchState, type TreeItem } from '../taxonomy/tree-model';
    import { portal } from '../utils/portal';
    import { isHoverPointer, isKeyboardFocus, TaxonPeek } from '../utils/taxon-peek.svelte';
    import TaxonCard from './TaxonCard.svelte';
    import { logger } from '../utils/logger';

    /**
     * The full family tree for one bird: a horizontal tree centred on it, as taxonomy trees are
     * usually drawn, with the fan and an indented outline as other views of the same data.
     *
     * It opens on the path from the class down to the bird, every rank on it expanded. An open
     * branch shows the taxa on that path and those seen at this feeder, and sums the rest in one
     * node that opens them all. Branches load as they open, so the 11,000 birds never load at once.
     * It is a ranked classification as the sources publish it, not an evolutionary timeline.
     */
    interface Props {
        /** The bird's lineage, root first, as the lineage route returns it. */
        lineage: Taxon[];
        onclose: () => void;
    }

    let { lineage, onclose }: Props = $props();

    type Mode = 'tree' | 'fan' | 'outline';
    const MODE_KEY = 'yawamf_family_tree_mode';
    let mode = $state<Mode>('tree');

    const principal = $derived(lineage.filter((taxon) => taxon.principal));
    // The tree starts at the class: above it, a bird's lineage is one line (Animalia, Chordata),
    // shown as the breadcrumb rather than as branches nobody needs to open.
    const rootIndex = $derived(Math.max(0, principal.findIndex((taxon) => taxon.rank === 'class')));
    const root = $derived(principal[rootIndex]);
    const above = $derived(principal.slice(0, rootIndex));
    const pathTaxa = $derived(principal.slice(rootIndex));
    const path = $derived(new Set(pathTaxa.map((taxon) => taxon.taxon_id)));
    const current = $derived(pathTaxa[pathTaxa.length - 1] ?? null);

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

    function showAll(parentId: number): void {
        setBranch(parentId, { showAll: true });
    }

    const layout = $derived(
        root
            ? layoutTree(
                  visibleTree({ root, branches, expanded, path, currentId: current?.taxon_id ?? null })
              )
            : null
    );

    // Tree geometry.
    const COLUMN = 210;
    const ROW = 40;
    const INSET = 36;
    // Room left of the root for its centred label.
    const LEAD = 80;
    const LABEL = 220;
    const treeWidth = $derived(layout ? LEAD + INSET + layout.depth * COLUMN + LABEL : 0);
    const treeHeight = $derived(layout ? INSET * 2 + (layout.rows - 1) * ROW + 24 : 0);
    // Fan geometry: the root at the centre, ranks in rings.
    const RING = 120;
    const fanRadius = $derived(layout ? layout.depth * RING + 170 : 0);
    // A few open branches would splay round the whole circle; the fan widens as rows are added.
    const fanSweep = $derived(Math.min(Math.PI * 1.6, Math.max(Math.PI * 0.6, (layout?.rows ?? 1) * 0.3)));

    function position(node: PlacedNode<TreeItem>): { x: number; y: number } {
        if (mode === 'fan' && layout) {
            const point = fanPoint(node, layout.rows, RING, fanSweep);
            return { x: fanRadius + point.x, y: fanRadius + point.y };
        }
        const point = treePoint(node, COLUMN, ROW, INSET);
        return { x: point.x + LEAD - INSET, y: point.y };
    }

    const byId = $derived(new Map((layout?.nodes ?? []).map((node) => [node.id, node])));
    // On the tree an open group's branches leave to the right, so its label sits above the node
    // rather than across them; leaves keep theirs beside the node.
    const branching = $derived(new Set((layout?.links ?? []).map((link) => link.from)));

    function linkPath(fromId: string, toId: string): string {
        const from = byId.get(fromId);
        const to = byId.get(toId);
        if (!from || !to) return '';
        const a = position(from);
        const b = position(to);
        if (mode === 'fan') return `M${a.x},${a.y}L${b.x},${b.y}`;
        const mid = (a.x + b.x) / 2;
        return `M${a.x},${a.y}C${mid},${a.y} ${mid},${b.y} ${b.x},${b.y}`;
    }

    function onPathLink(toId: string): boolean {
        const node = byId.get(toId);
        return node?.data.kind === 'taxon' && node.data.onPath;
    }

    function activate(item: TreeItem, element?: Element): void {
        if (item.kind === 'more') showAll(item.parentId);
        // A species has nothing beneath it to open, so selecting it shows its card.
        else if (item.taxon.rank === 'species') {
            if (element) peek.toggle(item.taxon, item.current, element);
        } else {
            peek.close();
            toggle(item.taxon);
        }
    }

    function peekHover(event: PointerEvent, item: TreeItem): void {
        if (item.kind === 'taxon' && isHoverPointer(event)) peek.hover(item.taxon, item.current, event.currentTarget as Element);
    }

    function peekFocus(event: FocusEvent, item: TreeItem): void {
        if (item.kind === 'taxon' && isKeyboardFocus(event.currentTarget)) peek.focus(item.taxon, item.current, event.currentTarget as Element);
    }

    function nodeLabel(item: TreeItem): string {
        if (item.kind === 'more') {
            return $_('taxonomy.more', { values: { count: item.hidden }, default: '{count} more' });
        }
        return taxonLabel(item.taxon);
    }

    function seenText(taxon: Taxon): string | null {
        if (taxon.rank === 'species') {
            return (taxon.seen_count ?? 0) > 0
                ? $_('taxonomy.captures_here', { values: { count: taxon.seen_count }, default: '{count} captures here' })
                : null;
        }
        return isSeen(taxon)
            ? $_('taxonomy.seen_here', { values: { count: taxon.seen_species }, default: '{count} seen here' })
            : null;
    }

    function ariaFor(item: TreeItem): string {
        if (item.kind === 'more') return nodeLabel(item);
        const parts = [taxonLabel(item.taxon), $_(`taxonomy.rank.${item.taxon.rank}`, { default: item.taxon.rank })];
        const seen = seenText(item.taxon);
        if (seen) parts.push(seen);
        if (item.current) parts.push($_('taxonomy.this_bird', { default: 'this bird' }));
        return parts.join(', ');
    }

    function onNodeKey(event: KeyboardEvent, item: TreeItem): void {
        if (event.key === 'Enter' || event.key === ' ') {
            event.preventDefault();
            activate(item, event.currentTarget as Element);
        }
    }

    // Outline: the same visible tree, indented, as plain disclosure buttons.
    const outline = $derived(layout?.nodes ?? []);

    let scroller = $state<HTMLElement | null>(null);
    let dialog = $state<HTMLElement | null>(null);

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

    onMount(() => {
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
        return () => window.removeEventListener('keydown', onKey, true);
    });
</script>

<div
    use:portal
    class="fixed inset-0 z-[80] flex items-center justify-center bg-slate-950/70 p-0 backdrop-blur-sm sm:p-4"
    role="presentation"
    onclick={(event) => {
        if (event.target === event.currentTarget) onclose();
    }}
>
    <div
        bind:this={dialog}
        class="flex h-[100dvh] w-full max-w-6xl flex-col overflow-hidden bg-white shadow-2xl dark:bg-slate-900 sm:h-[90dvh] sm:rounded-2xl sm:border sm:border-white/10"
        role="dialog"
        aria-modal="true"
        aria-labelledby="family-tree-title"
        tabindex="-1"
        data-family-tree
    >
        <header class="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 px-4 py-3 dark:border-slate-800 sm:px-6">
            <div class="min-w-0">
                <h2 id="family-tree-title" class="font-display text-xl font-bold text-slate-900 dark:text-white">
                    {$_('taxonomy.title', { values: { name: current ? taxonLabel(current) : '' }, default: 'Family tree of {name}' })}
                </h2>
                {#if above.length > 0}
                    <p class="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                        {[...above, root].filter(Boolean).map((taxon) => taxonLabel(taxon)).join(' › ')}
                    </p>
                {/if}
            </div>
            <div class="flex items-center gap-2">
                <div class="inline-flex overflow-hidden rounded-lg border border-slate-200 dark:border-slate-700" role="group" aria-label={$_('taxonomy.layouts', { default: 'Layout' })}>
                    {#each [['tree', $_('taxonomy.layout_tree', { default: 'Tree' })], ['fan', $_('taxonomy.layout_fan', { default: 'Fan' })], ['outline', $_('taxonomy.layout_outline', { default: 'Outline' })]] as [value, text] (value)}
                        <button
                            type="button"
                            class="px-3 py-1.5 text-xs font-semibold transition-colors {mode === value ? 'bg-brand-600 text-white' : 'bg-white text-slate-600 hover:bg-slate-100 dark:bg-slate-900 dark:text-slate-300 dark:hover:bg-slate-800'}"
                            aria-pressed={mode === value}
                            onclick={() => setMode(value as Mode)}
                            data-family-tree-mode={value}
                        >{text}</button>
                    {/each}
                </div>
                <button type="button" class="btn btn-ghost text-sm" onclick={onclose} data-family-tree-close>
                    {$_('common.close', { default: 'Close' })}
                </button>
            </div>
        </header>

        <div class="flex flex-wrap gap-x-4 gap-y-1 px-4 pt-2 text-[11px] text-slate-500 dark:text-slate-400 sm:px-6">
            <span><span class="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-amber-400 align-middle"></span>{$_('taxonomy.legend_path', { default: 'Path to this bird' })}</span>
            <span><span class="mr-1 inline-block h-2.5 w-2.5 rounded-full bg-emerald-500 align-middle"></span>{$_('taxonomy.legend_seen', { default: 'Seen at this feeder' })}</span>
            <span>{$_('taxonomy.legend_open', { default: 'Select a group to open or close it' })}</span>
        </div>

        <div bind:this={scroller} class="relative min-h-0 flex-1 overflow-auto px-2 py-2 sm:px-4" data-family-tree-canvas>
            {#if !layout}
                <p class="p-6 text-sm text-slate-500">{$_('taxonomy.loading', { default: 'Loading the family tree' })}</p>
            {:else if mode === 'outline'}
                <ul class="space-y-0.5 py-2" aria-label={$_('taxonomy.outline_label', { default: 'Family tree outline' })} data-family-tree-outline>
                    {#each outline as node (node.id)}
                        {@const item = node.data}
                        <li style:padding-left="{node.depth * 20}px">
                            <button
                                type="button"
                                class="flex w-full min-h-11 items-center gap-2 rounded-lg px-2 py-1.5 text-left hover:bg-slate-100 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 dark:hover:bg-slate-800"
                                aria-expanded={item.kind === 'taxon' ? (item.expandable ? item.expanded : peek.isOpen(item.taxon.taxon_id)) : undefined}
                                aria-current={item.kind === 'taxon' && item.current ? 'true' : undefined}
                                onclick={(event) => activate(item, event.currentTarget)}
                                onpointerenter={(event) => peekHover(event, item)}
                                onpointerleave={() => peek.leave()}
                                onfocus={(event) => peekFocus(event, item)}
                                onblur={() => peek.leave()}
                                data-taxon-peek-trigger
                            >
                                <span class="w-3 text-slate-400" aria-hidden="true">{item.kind === 'taxon' && item.expandable ? (item.expanded ? '▾' : '▸') : ''}</span>
                                {#if item.kind === 'more'}
                                    <span class="text-sm text-slate-500">{nodeLabel(item)}</span>
                                {:else}
                                    <span class="text-sm font-semibold {item.current ? 'text-amber-600 dark:text-amber-300' : 'text-slate-900 dark:text-white'}">{taxonLabel(item.taxon)}</span>
                                    {#if item.taxon.name}<span class="hidden text-xs italic text-slate-500 sm:inline">{item.taxon.scientific_name}</span>{/if}
                                    <span class="text-[10px] uppercase tracking-wide text-slate-400">{$_(`taxonomy.rank.${item.taxon.rank}`, { default: item.taxon.rank })}</span>
                                    {#if seenText(item.taxon)}<span class="ml-auto shrink-0 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700 dark:bg-emerald-950/50 dark:text-emerald-300">{seenText(item.taxon)}</span>{/if}
                                {/if}
                            </button>
                        </li>
                    {/each}
                </ul>
            {:else}
                {@const size = mode === 'fan' ? { width: fanRadius * 2 + LABEL, height: fanRadius * 2 } : { width: treeWidth, height: treeHeight }}
                <div class="flex min-h-full min-w-full">
                <svg width={size.width} height={size.height} class="m-auto block shrink-0" data-family-tree-svg={mode}>
                    {#each layout.links as link (link.to)}
                        <path
                            d={linkPath(link.from, link.to)}
                            fill="none"
                            class={onPathLink(link.to) ? 'stroke-amber-400' : 'stroke-slate-300 dark:stroke-slate-600'}
                            stroke-width={onPathLink(link.to) ? 2.4 : 1.2}
                        />
                    {/each}
                    {#each layout.nodes as node (node.id)}
                        {@const item = node.data}
                        {@const point = position(node)}
                        {@const left = mode === 'fan' && point.x < fanRadius - 1}
                        {@const labelAbove = mode === 'tree' && branching.has(node.id)}
                        {@const named = item.kind === 'taxon' && item.taxon.name !== null}
                        <g
                            transform="translate({point.x},{point.y})"
                            role="button"
                            tabindex="0"
                            aria-label={ariaFor(item)}
                            aria-expanded={item.kind === 'taxon' ? (item.expandable ? item.expanded : peek.isOpen(item.taxon.taxon_id)) : undefined}
                            class="tree-node cursor-pointer focus:outline-none"
                            onclick={(event) => activate(item, event.currentTarget)}
                            onkeydown={(event) => onNodeKey(event, item)}
                            onpointerenter={(event) => peekHover(event, item)}
                            onpointerleave={() => peek.leave()}
                            onfocus={(event) => peekFocus(event, item)}
                            onblur={() => peek.leave()}
                            data-taxon-peek-trigger
                            data-family-tree-node={item.kind === 'taxon' ? item.taxon.taxon_id : `more:${item.parentId}`}
                        >
                            <circle
                                r={item.kind === 'taxon' && item.current ? 7 : item.kind === 'more' ? 4 : 5.5}
                                class={item.kind === 'more'
                                    ? 'fill-slate-200 stroke-slate-400 dark:fill-slate-700'
                                    : item.current
                                      ? 'fill-amber-400 stroke-amber-500'
                                      : isSeen(item.taxon)
                                        ? 'fill-emerald-500 stroke-emerald-600'
                                        : item.expandable && !item.expanded
                                          ? 'fill-slate-400 stroke-slate-500 dark:fill-slate-500'
                                          : 'fill-white stroke-slate-400 dark:fill-slate-900'}
                                stroke-width={item.kind === 'taxon' && item.onPath ? 2.4 : 1.4}
                            />
                            <circle r="14" class="focus-ring fill-transparent stroke-brand-500" stroke-width="2" />
                            <text
                                x={labelAbove ? 0 : left ? -12 : 12}
                                y={labelAbove ? (named ? -22 : -12) : named && mode === 'tree' ? -2 : 4}
                                text-anchor={labelAbove ? 'middle' : left ? 'end' : 'start'}
                                class="tree-label text-[12px] font-semibold {item.kind === 'more' ? 'fill-slate-500' : item.current ? 'fill-amber-600 dark:fill-amber-300' : 'fill-slate-800 dark:fill-slate-100'}"
                            >
                                {nodeLabel(item)}{#if item.kind === 'taxon' && seenText(item.taxon)}<tspan class="fill-emerald-600 dark:fill-emerald-400 font-normal">{`\u00a0· ${seenText(item.taxon)}`}</tspan>{/if}
                            </text>
                            {#if item.kind === 'taxon' && named && mode === 'tree'}
                                <text x={labelAbove ? 0 : 12} y={labelAbove ? -10 : 12} text-anchor={labelAbove ? 'middle' : 'start'} class="tree-label fill-slate-500 text-[10.5px] italic dark:fill-slate-400">{item.taxon.scientific_name}</text>
                            {/if}
                        </g>
                    {/each}
                </svg>
                </div>
            {/if}
        </div>

        <footer class="border-t border-slate-200 px-4 py-2 text-[11px] text-slate-500 dark:border-slate-800 dark:text-slate-400 sm:px-6">
            {#if failed}
                <span class="mr-2 font-semibold text-amber-700 dark:text-amber-300">{$_('taxonomy.branch_failed', { default: 'Part of the tree could not load. Open it again to retry.' })}</span>
            {/if}
            {$_('taxonomy.source_note', { default: 'Classification from the IOC World Bird List for birds and the Catalogue of Life above them. It shows how species are grouped, not when they diverged.' })}
        </footer>
    </div>
</div>

<TaxonCard {peek} />


<style>
    /* A halo in the canvas colour, so a branch passing behind a label never strikes it through. */
    .tree-label {
        paint-order: stroke;
        stroke: white;
        stroke-width: 4px;
        stroke-linejoin: round;
    }
    :global(.dark) .tree-label {
        stroke: rgb(15 23 42);
    }
    .tree-node .focus-ring {
        opacity: 0;
    }
    .tree-node:focus-visible .focus-ring {
        opacity: 1;
    }
</style>
