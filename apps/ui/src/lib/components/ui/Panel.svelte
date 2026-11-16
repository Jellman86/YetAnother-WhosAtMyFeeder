<script lang="ts">
    import type { Snippet } from 'svelte';

    /**
     * A standing section on the page: one hairline and a flat panel fill (`card-base`), a heading
     * that names it, and optional actions beside the heading. A panel is told apart by its
     * heading, never by a tint, so it takes no tone.
     */
    type Props = {
        title?: string;
        description?: string;
        headingLevel?: 2 | 3;
        actions?: Snippet;
        children: Snippet;
        /** `none` for a panel whose rows run to its edges. */
        padding?: 'md' | 'none';
        as?: 'section' | 'div' | 'article';
        class?: string;
        /** Hooks for tests and captures, such as `data-health-timeline`. */
        [data: `data-${string}`]: string | boolean | undefined;
    };

    let {
        title,
        description,
        headingLevel = 2,
        actions,
        children,
        padding = 'md',
        as = 'section',
        class: className = '',
        ...data
    }: Props = $props();

    const headingId = $props.id();
</script>

<svelte:element
    this={as}
    class="card-base min-w-0 {padding === 'md' ? 'p-5' : ''} {className}"
    aria-labelledby={title ? headingId : undefined}
    {...data}
>
    {#if title || actions}
        <div class="flex flex-wrap items-start justify-between gap-x-3 gap-y-2 {padding === 'none' ? 'px-5 pt-5' : ''}">
            {#if title}
                <div class="min-w-0 flex-1 basis-48">
                    <svelte:element this={`h${headingLevel}`} id={headingId} class="font-display font-bold text-strong wrap-break-word {headingLevel === 2 ? 'text-xl' : 'text-lg'}">{title}</svelte:element>
                    {#if description}
                        <p class="mt-1 text-sm text-muted">{description}</p>
                    {/if}
                </div>
            {/if}
            {#if actions}
                <div class="ml-auto flex flex-wrap items-center gap-2">{@render actions()}</div>
            {/if}
        </div>
    {/if}
    {@render children()}
</svelte:element>
