<script lang="ts">
    import type { Snippet } from 'svelte';

    interface Props {
        title: string;
        description?: string;
        // Optional emoji or icon snippet rendered in the leading tile.  Kept
        // monochrome on the outside so per-tab colours stop signalling product
        // differences they don't actually mean.
        icon?: string;
        iconSnippet?: Snippet;
        // Trailing controls rendered next to the header (e.g. "Test connection",
        // "Clear history").  Kept in the header so every card has the same
        // top-level affordance position.
        actions?: Snippet;
        children: Snippet;
    }

    let { title, description, icon, iconSnippet, actions, children }: Props = $props();
</script>

<section class="card-base rounded-3xl p-6 md:p-8 backdrop-blur-md">
    <header class="flex items-start justify-between gap-4 mb-6">
        <div class="flex items-start gap-3 min-w-0">
            {#if icon || iconSnippet}
                <div class="flex items-center justify-center w-10 h-10 rounded-2xl bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 flex-shrink-0">
                    {#if iconSnippet}
                        {@render iconSnippet()}
                    {:else}
                        <span class="text-xl" aria-hidden="true">{icon}</span>
                    {/if}
                </div>
            {/if}
            <div class="min-w-0">
                <h3 class="text-lg md:text-xl font-black text-slate-900 dark:text-white tracking-tight">
                    {title}
                </h3>
                {#if description}
                    <p class="text-[10px] font-black uppercase tracking-widest text-slate-500 dark:text-slate-400 mt-1">
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
