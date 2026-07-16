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
        children: Snippet;
    }

    let { title, description, iconSnippet, actions, children }: Props = $props();
</script>

<section class="card-base rounded-3xl p-6 md:p-8 backdrop-blur-md">
    <header class="flex items-start justify-between gap-4 mb-6">
        <div class="flex items-start gap-3 min-w-0">
            {#if iconSnippet}
                <div class="flex items-center justify-center w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 flex-shrink-0">
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

    <div class="space-y-4">
        {@render children()}
    </div>
</section>
