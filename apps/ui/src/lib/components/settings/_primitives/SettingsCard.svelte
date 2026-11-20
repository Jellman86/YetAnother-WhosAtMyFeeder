<script lang="ts">
    import type { Snippet } from 'svelte';
    import { useDisclosure } from '../../../settings/disclosures.svelte';
    import { markInsideCard } from '../../ui/surface';
    import { provideSubheadingLevel } from './heading-level';

    interface Props {
        title: string;
        description?: string;
        // Trailing controls beside the heading, such as the switch for the whole section.
        actions?: Snippet;
        /**
         * Sections that start closed: the heading becomes a button that shows the body.
         * The id names the body for aria-controls.
         */
        collapsible?: boolean;
        /** Whether a collapsible section starts open, until someone opens or closes it. */
        openByDefault?: boolean;
        id?: string;
        /** The heading's id, so a switch in the header can be named by the section's own title. */
        titleId?: string;
        /** A card inside a section's More options, under its heading: one level down. */
        nested?: boolean;
        /** A card on a page that has no section heading above it (Health): directly under the page title. */
        underPageTitle?: boolean;
        children: Snippet;
    }

    let { title, description, actions, collapsible = false, openByDefault = false, id, titleId, nested = false, underPageTitle = false, children }: Props = $props();

    const uid = $props.id();
    markInsideCard();
    // The page is h1, the open section h2, a group h3, and a group under More options h4. A
    // subheading inside the card is one below the card's own.
    const tag = $derived(underPageTitle ? 'h2' : nested ? 'h4' : 'h3');
    provideSubheadingLevel(() => (nested ? 5 : 4));
    const headingId = $derived(titleId ?? `${id ?? uid}-title`);

    // With an id, the Settings page holds the open state, so it survives leaving the tab and the
    // page can open the section that holds a refused field.
    const disclosure = useDisclosure(() => ({ id, openByDefault }));
    const open = $derived(disclosure.open);
    const bodyId = $derived(`${id ?? uid}-body`);
    const showBody = $derived(!collapsible || open);
</script>

<!-- A group is a display-face heading over one raised card of rows: no icon, no band, nothing boxed inside.
     The actions sit beside the heading while it keeps at least 12rem, and wrap under it when not;
     The heading starts on the card's own left edge, as the section's name and status do;
     the header's right inset matches the card's, so a section switch ends where row switches do. -->
<section class="space-y-3" {id} aria-labelledby={headingId} data-settings-section>
    <header class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 pr-4 md:pr-6">
        <div class="min-w-0 flex-1 basis-48">
            <svelte:element this={tag} id={headingId} class="font-display font-semibold text-strong {nested ? 'text-lg' : 'text-xl'}">
                {#if collapsible}
                    <button
                        type="button"
                        class="focus-ring flex min-h-11 max-w-full items-center gap-2 rounded-lg text-left"
                        aria-expanded={open}
                        aria-controls={bodyId}
                        onclick={() => disclosure.toggle()}
                    >
                        <span class="min-w-0 wrap-break-word">{title}</span>
                        <svg class="h-4 w-4 shrink-0 text-slate-600 transition-transform motion-reduce:transition-none dark:text-slate-400 {open ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
                    </button>
                {:else}
                    {title}
                {/if}
            </svelte:element>
            {#if description}
                <p class="mt-1 max-w-prose text-sm leading-relaxed text-muted">{description}</p>
            {/if}
        </div>
        {#if actions}
            <div class="flex min-h-11 max-w-full shrink-0 items-center">
                {@render actions()}
            </div>
        {/if}
    </header>

    {#if showBody}
        <div id={bodyId} class="card-base settings-section-body" data-settings-section-body>
            {@render children()}
        </div>
    {/if}
</section>
