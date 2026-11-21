<script lang="ts">
    import type { Snippet } from 'svelte';
    import { portal } from '../../utils/portal';
    import { trapFocus } from '../../utils/focus-trap';
    import { lockDocumentScroll } from '../../utils/document-scroll-lock';
    import DialogHeader from './DialogHeader.svelte';

    /**
     * Filters on a phone or a narrow window: a modal sheet over the page, the app's dialog pattern
     * (named by the shared header, portalled, focus held inside and handed back, Escape or the round
     * close button to leave, the page still beneath it). It rises from the bottom on a phone and
     * slides in from the right on a tablet.
     */
    type Props = {
        title: string;
        onclose: () => void;
        /** The sheet's id, for the opener's aria-controls. */
        id: string;
        children: Snippet;
        closeData?: Record<`data-${string}`, string | boolean>;
        [data: `data-${string}`]: string | boolean | undefined;
    };

    let { title, onclose, id, children, closeData = {}, ...data }: Props = $props();

    const titleId = $props.id();
    let sheet = $state<HTMLDivElement | null>(null);

    function handleKeydown(event: KeyboardEvent): void {
        // Keys pressed in a modal belong to it, not to the page's shortcuts beneath.
        event.stopPropagation();
        if (event.key === 'Escape') {
            event.preventDefault();
            onclose();
        }
    }

    // The page's scroll and focus are outside Svelte: hold both while the sheet is open.
    $effect(() => {
        if (!sheet) return;
        const unlock = lockDocumentScroll();
        const release = trapFocus(sheet);
        return () => {
            release();
            unlock();
        };
    });
</script>

<div
    class="fixed inset-0 z-60 flex items-end justify-center bg-media/70 sm:items-stretch sm:justify-end"
    use:portal
    role="presentation"
    onclick={(event) => { if (event.target === event.currentTarget) onclose(); }}
>
    <div
        bind:this={sheet}
        {id}
        class="flex max-h-sheet w-full flex-col overflow-hidden rounded-t-3xl border border-line bg-surface text-strong shadow-2xl sm:h-full sm:max-h-none sm:max-w-sm sm:rounded-none sm:rounded-l-3xl"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabindex="-1"
        onkeydown={handleKeydown}
        {...data}
    >
        <DialogHeader {title} {titleId} onClose={onclose} {closeData} />
        <div class="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto overscroll-contain px-4 py-4">
            {@render children()}
        </div>
    </div>
</div>
