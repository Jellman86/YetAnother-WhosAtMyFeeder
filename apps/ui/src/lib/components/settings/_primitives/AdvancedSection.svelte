<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { settingsDisclosures } from '../../../settings/disclosure-context';

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

    // With an id, the Settings page holds the open state, so it survives leaving the tab and the
    // page can open the section that holds a refused field.
    const disclosures = settingsDisclosures();
    let userOpen = $state<boolean | null>(null);
    const open = $derived((id && disclosures ? disclosures.isOpen(id) : userOpen ?? undefined) ?? openByDefault);
    function toggle(): void {
        if (id && disclosures) disclosures.setOpen(id, !open);
        else userOpen = !open;
    }
    const contentId = $derived(id ? `${id}-content` : undefined);
</script>

<div class="rounded-2xl border border-dashed border-line">
    <button
        type="button"
        aria-expanded={open}
        aria-controls={contentId}
        onclick={toggle}
        class="flex min-h-11 w-full cursor-pointer items-center justify-between gap-3 rounded-2xl px-4 py-3 text-left focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-brand-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-950"
    >
        <span class="flex min-w-0 flex-wrap items-center gap-2">
            <span class="rounded-md border border-line px-2 py-0.5 text-xs font-semibold text-slate-700 dark:text-slate-200">
                {$_('settings.common.advanced', { default: 'Advanced' })}
            </span>
            <span class="min-w-0 wrap-break-word text-sm font-semibold text-slate-700 dark:text-slate-200">
                {title ?? $_('settings.common.advanced_default_title', { default: 'Advanced options' })}
            </span>
        </span>
        <svg
            class="w-4 h-4 shrink-0 text-slate-400 transition-transform duration-200 {open ? 'rotate-180' : ''}"
            viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"
            aria-hidden="true"
        >
            <polyline points="6 9 12 15 18 9"/>
        </svg>
    </button>
    {#if open}
        <div id={contentId} class="space-y-4 px-4 pb-4 pt-1">
            {#if description}
                <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-400">{description}</p>
            {/if}
            {@render children()}
        </div>
    {/if}
</div>
