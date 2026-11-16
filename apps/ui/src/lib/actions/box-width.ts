/**
 * Says whether the node is at least as wide as its `[data-room-ruler]` child: the same question a
 * container query asks, so a layout can build only the arrangement that fits instead of building
 * both and hiding one. The ruler is a zero-height element sized in `rem`, so a larger text size,
 * which widens the ruler and not the node, is followed too; clip it so it never widens the page.
 *
 * The first answer is read as the node mounts, while it is still empty: a ResizeObserver answers
 * only after a paint, and the page would show without either arrangement and then jump. Later
 * changes (a resized window, a larger text size) come from the observer.
 */
export function roomFor(node: HTMLElement, onRoom: (fits: boolean) => void): { destroy(): void } {
    const ruler = node.querySelector<HTMLElement>('[data-room-ruler]');
    if (!ruler) return { destroy() {} };
    const measure = (): void => onRoom(node.clientWidth >= ruler.clientWidth);
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    observer.observe(ruler);
    return { destroy: () => observer.disconnect() };
}
