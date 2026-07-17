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
        children: Snippet;
    }

    let { title, description, iconSnippet, actions, accent = false, children }: Props = $props();
</script>

<section class="card-base overflow-hidden rounded-3xl backdrop-blur-md">
    <header class="flex items-start justify-between gap-4 px-6 md:px-8 pt-6 md:pt-8 pb-6">
        <div class="flex items-start gap-3 min-w-0">
            {#if iconSnippet}
                <div
                    class="flex items-center justify-center w-10 h-10 rounded-2xl flex-shrink-0
                           {accent
                               ? 'bg-teal-500/15 text-teal-700 dark:bg-teal-400/15 dark:text-teal-300'
                               : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200'}"
                >
                    {@render iconSnippet()}
                </div>
            {/if}
            <div class="min-w-0">
                <h3 class="text-lg md:text-xl font-black text-slate-900 dark:text-white tracking-tight">
                    {title}
                </h3>
                {#if description}
                    <p class="mt-1 text-sm font-medium leading-relaxed text-slate-600 dark:text-slate-400">
                        {description}
                    </p>
                {/if}
            </div>
        </div>
        {#if actions}
            <div class="flex-shrink-0">
                {@render actions()}
            </div>
        {/if}
    </header>

    <div class="space-y-4 px-6 md:px-8 pb-6 md:pb-8">
        {@render children()}
    </div>
</section>
