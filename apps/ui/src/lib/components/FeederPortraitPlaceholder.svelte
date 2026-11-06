<script lang="ts">
    import { _ } from 'svelte-i18n';

    /**
     * The portrait's shape while its facts are read: the latest visit's media box and the fact rows
     * at their real sizes, so the colophon beneath stays where it is when the portrait lands. A
     * failed read keeps one quiet line of fixed height instead.
     */
    interface Props {
        failed?: boolean;
        /** The install count is known, so the portrait will close with its line. */
        withCommunity?: boolean;
    }

    let { failed = false, withCommunity = false }: Props = $props();

    const bar = 'block rounded bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-700/60';
</script>

{#if failed}
    <p class="flex min-h-11 items-center text-sm text-slate-500 dark:text-slate-400" data-feeder-portrait-unavailable>
        {$_('about.portrait.unavailable', { default: "This feeder's facts could not be loaded." })}
    </p>
{:else}
    <div class="grid gap-5 md:grid-cols-2 md:items-center" aria-busy="true" data-feeder-portrait-loading>
        <p role="status" class="sr-only">{$_('about.portrait.loading', { default: "Loading this feeder's facts…" })}</p>
        <div class="aspect-video w-full rounded-2xl bg-slate-200/80 animate-pulse motion-reduce:animate-none dark:bg-slate-800" aria-hidden="true" data-loading-placeholder></div>
        <div class="min-w-0 space-y-4" aria-hidden="true">
            <!-- One line of the heading, at its line height. -->
            <span class="flex h-7 items-center"><span class="{bar} h-5 w-3/4" data-loading-placeholder></span></span>
            <div class="grid grid-cols-2 gap-x-6 gap-y-4">
                {#each ['w-16', 'w-12'] as width (width)}
                    <div>
                        <span class="flex h-8 items-center"><span class="{bar} h-6 {width}" data-loading-placeholder></span></span>
                        <span class="flex h-4 items-center"><span class="{bar} h-2.5 w-10" data-loading-placeholder></span></span>
                    </div>
                {/each}
                {#each ['w-24', 'w-20'] as width (width)}
                    <div>
                        <span class="flex h-4 items-center"><span class="{bar} h-2.5 w-16" data-loading-placeholder></span></span>
                        <span class="mt-0.5 flex min-h-[44px] items-center"><span class="{bar} h-3.5 {width}" data-loading-placeholder></span></span>
                        <span class="flex h-4 items-center"><span class="{bar} h-2.5 w-14" data-loading-placeholder></span></span>
                    </div>
                {/each}
            </div>
            {#if withCommunity}
                <span class="flex h-4 items-center"><span class="{bar} h-2.5 w-48 max-w-full" data-loading-placeholder></span></span>
            {/if}
        </div>
    </div>
{/if}
