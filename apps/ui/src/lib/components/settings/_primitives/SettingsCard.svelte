<script lang="ts">
    import type { Snippet } from 'svelte';

    interface Props {
        title: string;
        description?: string;
        // Optional vector/brand icon rendered in the leading tile. Structural
        // emoji are intentionally unsupported so card hierarchy stays stable
        // across operating systems and locales.
        iconSnippet?: Snippet;
        // Trailing controls rendered next to the header (e.g. "Test connection",
        // "Clear history").  Kept in the header so every card has the same
        // top-level affordance position.
        actions?: Snippet;
        // When true the leading icon tile is tinted teal to give a card a light
        // brand accent. Off by default (slate tile). The header itself stays plain
        // either way — no gradient band.
        accent?: boolean;
        /**
         * Advanced cards start closed: the heading becomes a button that shows the card's body.
         * The id names the body for aria-controls.
         */
        collapsible?: boolean;
        /** Whether a collapsible card is open; bind it to open the card from elsewhere. */
        open?: boolean;
        id?: string;
        children: Snippet;
    }

    let { title, description, iconSnippet, actions, accent = false, collapsible = false, open = $bindable(false), id, children }: Props = $props();

    const bodyId = $derived(id ? `${id}-body` : undefined);
    const showBody = $derived(!collapsible || open);
</script>

<section class="card-base overflow-hidden" {id}>
    <header class="flex items-start justify-between gap-4 px-5 pt-5 pb-4 md:px-6 md:pt-6">
        <div class="flex items-start gap-3 min-w-0">
            {#if iconSnippet}
                <div class="mt-0.5 shrink-0 {accent ? 'text-brand-700 dark:text-brand-300' : 'text-slate-600 dark:text-slate-400'}">
                    {@render iconSnippet()}
                </div>
            {/if}
            <div class="min-w-0">
                <!-- Cards are the sections of a tab, directly under the page heading. -->
                <h2 class="font-display text-lg font-semibold text-slate-900 dark:text-white">
                    {#if collapsible}
                        <button
                            type="button"
                            class="flex min-h-11 max-w-full items-center gap-2 rounded-lg text-left focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500"
                            aria-expanded={open}
                            aria-controls={bodyId}
                            onclick={() => (open = !open)}
                        >
                            <span class="min-w-0 wrap-break-word">{title}</span>
                            <svg class="h-4 w-4 shrink-0 text-slate-500 transition-transform motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                        </button>
                    {:else}
                        {title}
                    {/if}
                </h2>
                {#if description}
                    <p class="mt-1 text-sm leading-relaxed text-slate-600 dark:text-slate-300">
                        {description}
                    </p>
                {/if}
            </div>
        </div>
        {#if actions}
            <div class="shrink-0">
                {@render actions()}
            </div>
        {/if}
    </header>

    {#if showBody}
        <div id={bodyId} class="space-y-4 px-5 pb-5 md:px-6 md:pb-6">
            {@render children()}
        </div>
    {/if}
</section>
