<script lang="ts">
    /**
     * A collapsible group of one beta feature's settings: a heading that is also the disclosure
     * button, so it reads as a heading and says whether it is open. A closed section stays mounted
     * and only hidden, so a download or a status read inside it keeps running.
     */
    import type { Snippet } from 'svelte';
    import { useDisclosure } from '../../settings/disclosures.svelte';

    interface Props {
        id: string;
        title: string;
        /** A short summary of the closed section, such as "Off" or "2 birds". */
        hint?: string;
        /** Open until someone closes it; the Settings page then remembers the choice by id. */
        openByDefault?: boolean;
        children: Snippet;
    }

    let { id, title, hint, openByDefault = false, children }: Props = $props();
    const disclosure = useDisclosure(() => ({ id, openByDefault }));
    const open = $derived(disclosure.open);
</script>

<div class="py-1" data-beta-section={id}>
    <h4>
        <button
            type="button"
            id={`${id}-toggle`}
            aria-expanded={open}
            aria-controls={`${id}-panel`}
            onclick={() => disclosure.toggle()}
            class="flex min-h-11 w-full items-center justify-between gap-3 rounded-lg py-2 text-left focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
        >
            <span class="min-w-0 wrap-break-word text-sm font-semibold text-slate-900 dark:text-white">{title}</span>
            <span class="flex shrink-0 items-center gap-2">
                {#if hint}<span class="text-xs text-slate-600 dark:text-slate-400" data-beta-section-hint>{hint}</span>{/if}
                <svg class="h-4 w-4 text-slate-600 motion-safe:transition-transform dark:text-slate-400 {open ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
                    <polyline points="6 9 12 15 18 9" />
                </svg>
            </span>
        </button>
    </h4>
    <div id={`${id}-panel`} class="space-y-4 pb-4 pt-1" hidden={!open}>
        {@render children()}
    </div>
</div>
