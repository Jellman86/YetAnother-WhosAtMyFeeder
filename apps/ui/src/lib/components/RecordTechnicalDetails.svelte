<script lang="ts">
    import type { Snippet } from 'svelte';
    import type { HTMLAttributes } from 'svelte/elements';

    /**
     * The identifiers and saved evidence of a record: closed by default, drawn as an ordinary
     * panel in the current theme, and always the last thing in its column so the keyboard
     * reaches it in the order it is seen.
     */
    let { title, identifier, children, ...attributes }: {
        title: string;
        identifier: string;
        children?: Snippet;
    } & HTMLAttributes<HTMLDetailsElement> = $props();
</script>

<details {...attributes} data-record-technical-details class="group card-base">
    <summary
        class="flex min-h-11 cursor-pointer list-none items-center justify-between gap-2 rounded-[inherit] px-3 py-1.5 text-xs font-semibold text-slate-700 marker:hidden focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-focus dark:text-slate-200"
    >
        <span class="min-w-0 wrap-anywhere">{title}</span>
        <svg class="h-3.5 w-3.5 shrink-0 text-slate-500 motion-safe:transition-transform group-open:rotate-180 dark:text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true">
            <path stroke-linecap="round" stroke-linejoin="round" d="m6 9 6 6 6-6" />
        </svg>
    </summary>
    <div class="border-t border-line-soft px-3 py-2.5 text-xs leading-relaxed text-slate-700 dark:text-slate-200">
        <p class="break-all font-mono" data-record-identifier>{identifier}</p>
        {#if children}{@render children()}{/if}
    </div>
</details>
