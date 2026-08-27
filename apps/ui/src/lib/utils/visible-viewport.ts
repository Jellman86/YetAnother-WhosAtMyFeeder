export interface VerticalBounds {
    top: number;
    height: number;
}

export interface VisualViewportBounds {
    offsetTop: number;
    height: number;
}

export function intersectVisibleViewport(
    container: VerticalBounds,
    viewport: VisualViewportBounds
): VerticalBounds {
    const containerBottom = container.top + container.height;
    const viewportBottom = viewport.offsetTop + viewport.height;
    const visibleTop = Math.max(container.top, viewport.offsetTop);
    const visibleBottom = Math.min(containerBottom, viewportBottom);

    return {
        top: Math.max(0, visibleTop - container.top),
        height: Math.max(0, visibleBottom - visibleTop)
    };
}
