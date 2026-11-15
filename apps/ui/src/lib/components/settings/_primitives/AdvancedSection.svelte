<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { useDisclosure } from '../../../settings/disclosures.svelte';

    interface Props {
        // Stable identifier for aria and test hooks. Inside Settings the page keeps
        // the open state by this id for the visit (it is not stored); callsites can
        // opt into an initially open state when work is already running inside.
        id?: string;
        title?: string;
        description?: string;
        openByDefault?: boolean;
        children: Snippet;
    }

    let { id, title, description, openByDefault = false, children }: Props = $props();

    const disclosure = useDisclosure(() => ({ id, openByDefault }));
    const open = $derived(disclosure.open);
    const contentId = $derived(id ? `${id}-content` : undefined);
</script>

<!-- A plain text disclosure at the end of its section: no border, no chip. The group's own name
     follows in muted text, so two on one tab can be told apart. -->
<div data-advanced-section>
    <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onclick={() => disclosure.toggle()}
        class="focus-ring inline-flex min-h-11 max-w-full cursor-pointer items-center gap-1.5 rounded-md text-left text-sm font-medium text-brand-700 hover:text-brand-800 dark:text-brand-300 dark:hover:text-brand-200"
    >
        <span class="min-w-0 wrap-break-word">
            {open
                ? $_('settings.common.hide_advanced', { default: 'Hide advanced options' })
                : $_('settings.common.show_advanced', { default: 'Show advanced options' })}{#if title}{' '}<span class="font-normal text-slate-600 dark:text-slate-400">({title})</span>{/if}
        </span>
        <svg
            class="h-4 w-4 shrink-0 transition-transform duration-200 motion-reduce:transition-none {open ? 'rotate-180' : ''}"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            aria-hidden="true"
        >
            <polyline points="6 9 12 15 18 9"/>
        </svg>
    </button>
    {#if open}
        <div id={contentId} class="settings-subrows mt-2">
            {#if description}
                <p class="max-w-prose text-sm leading-relaxed text-slate-600 dark:text-slate-400">{description}</p>
            {/if}
            {@render children()}
        </div>
    {/if}
</div>
