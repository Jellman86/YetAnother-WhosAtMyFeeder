/**
 * Svelte action that moves an element to a target container (default:
 * `document.body`) for the lifetime of the component.
 *
 * Overlays (`position: fixed` backdrops) must paint above all app chrome. When
 * they are rendered deep in the component tree, an ancestor with `transform`,
 * `filter`, or `backdrop-filter` establishes a stacking context that traps the
 * overlay's `z-index` — so a lower-`z` sticky header can paint over it. Portalling
 * the node to `<body>` removes it from that trap without changing Svelte
 * reactivity (the same node instance is simply re-parented).
 */
export function portal(node: HTMLElement, target: HTMLElement | string = document.body) {
    let targetEl: HTMLElement | null = null;

    function mount(t: HTMLElement | string): void {
        targetEl = typeof t === 'string' ? document.querySelector<HTMLElement>(t) : t;
        targetEl?.appendChild(node);
    }

    mount(target);

    return {
        update(t: HTMLElement | string) {
            mount(t);
        },
        destroy() {
            node.parentNode?.removeChild(node);
        }
    };
}
