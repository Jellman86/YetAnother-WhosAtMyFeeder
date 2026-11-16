<script lang="ts">
    import type { Snippet } from 'svelte';

    /**
     * The one disclosure: a full-width row naming what it holds, with a chevron that turns when it
     * opens, a 44px target and the kit focus ring (layout-patterns §6, "Disclosures"). What is chosen
     * inside a folded section can sit in `summary` beside its name, so a choice is never out of sight.
     */
    type Props = {
        label: string;
        /** A short note after the label, such as what is chosen inside. */
        note?: string;
        open?: boolean;
        children: Snippet;
        class?: string;
        [data: `data-${string}`]: string | boolean | undefined;
    };

    let { label, note, open = false, children, class: className = '', ...data }: Props = $props();
</script>

<details class="group {className}" {open} {...data}>
    <summary class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-lg px-1 text-xs font-semibold text-muted hover:bg-surface-raised hover:text-strong focus-ring [&::-webkit-details-marker]:hidden">
        <span class="min-w-0 wrap-break-word">
            {label}{#if note}<span class="font-semibold text-accent-ink"> · {note}</span>{/if}
        </span>
        <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path stroke-linecap="round" stroke-linejoin="round" d="m5 7.5 5 5 5-5" /></svg>
    </summary>
    <div class="mt-2">{@render children()}</div>
</details>
