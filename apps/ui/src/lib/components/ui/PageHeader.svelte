<script lang="ts">
    import type { Snippet } from 'svelte';

    /**
     * A page's one h1, with its subtitle and the page's own actions. The title takes the room; the
     * actions sit beside it while they fit and wrap below it when they do not, so enlarged text never
     * squeezes the title away. The subtitle always comes last, across the full width.
     */
    type Props = {
        title: string;
        subtitle?: string;
        actions?: Snippet;
    };

    let { title, subtitle, actions }: Props = $props();
</script>

<header class="mb-6 flex flex-wrap items-start justify-between gap-x-3 gap-y-1">
    <div class="page-title-block min-w-0 flex-1 basis-32 wrap-break-word">
        <h1 class="page-title font-display text-3xl font-bold leading-tight text-strong sm:text-4xl sm:leading-10">{title}</h1>
    </div>
    {#if subtitle}
        <p class="basis-full order-last text-base text-muted">{subtitle}</p>
    {/if}
    {#if actions}
        <div class="ml-auto flex max-w-full flex-wrap items-center justify-end gap-1">{@render actions()}</div>
    {/if}
</header>

<style>
    /* The title is never made smaller to fit: enlarged text must stay enlarged. In a column too
       narrow for one of its words (measured in rem, so this follows the text size), the word is
       hyphenated by the page's language, and broken anywhere only if that is not enough. */
    .page-title-block {
        container-type: inline-size;
    }

    @container (width < 16rem) {
        .page-title {
            hyphens: auto;
            overflow-wrap: anywhere;
        }
    }
</style>
