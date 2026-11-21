<script lang="ts">
    /**
     * The panel of a hover pop-out (`HoverPopout`): the larger look at a small capture.
     *
     * It is portalled out of its row and placed in viewport coordinates. Positioned inside the
     * row, it was clipped by any ancestor that hides its overflow, which the Explorer's list
     * frame does to round its corners, and it could be painted under a later row's controls.
     * Inside an open popover it is portalled into that popover, so it stays in the top layer.
     */
    import type { Snippet } from 'svelte';
    import type { HTMLAttributes } from 'svelte/elements';
    import { portal } from '../utils/portal';
    import type { HoverPopout } from '../utils/hover-popout.svelte';

    interface Props extends HTMLAttributes<HTMLDivElement> {
        popout: HoverPopout;
        /** Which of the controller's triggers this panel belongs to; its trigger is described by it. */
        index?: number;
        children: Snippet;
    }

    let { popout, index = 0, children, ...attributes }: Props = $props();
</script>

{#if popout.anchor}
    <div
        {...attributes}
        id={popout.panelId(index)}
        use:portal={popout.root?.closest<HTMLElement>('[popover]') ?? document.body}
        style="left: {popout.anchor.x}px; top: {popout.anchor.y}px;"
        class="fixed z-70 w-60 max-w-[calc(100vw-16px)] overflow-hidden rounded-2xl border border-slate-200 bg-surface shadow-2xl shadow-slate-950/20 animate-in fade-in zoom-in-95 motion-reduce:animate-none dark:border-slate-700 {popout.anchor.above
            ? '-translate-x-1/2 -translate-y-full'
            : '-translate-x-1/2'}"
        role="tooltip"
        onmouseenter={popout.cancelScheduledClose}
        onmouseleave={() => popout.hide()}
    >
        {@render children()}
    </div>
{/if}
