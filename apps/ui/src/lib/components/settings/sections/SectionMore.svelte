<script lang="ts">
    import type { Snippet } from 'svelte';
    import { _ } from 'svelte-i18n';
    import { useDisclosure } from '../../../settings/disclosures.svelte';
    import type { SettingsSection } from '../../../settings/settings-route';
    import { settingsMoreId } from '../../../settings/settings-more';

    interface Props {
        section: SettingsSection;
        /** What is inside, in a few words, so the closed row says what it holds. */
        summary: string;
        children: Snippet;
    }

    let { section, summary, children }: Props = $props();

    // The page keeps it open for the visit, and opens it for a refused value inside.
    const id = $derived(settingsMoreId(section));
    const disclosure = useDisclosure(() => ({ id, openByDefault: false }));
    const open = $derived(disclosure.open);
</script>

<!-- One "More options" per section, after the settings most owners need: everything else in the
     section, the developer-only settings in it marked Advanced. Its contents load when it opens.
     Its summary is in the reading face: the display face has no regular weight, so it came out bold.
     The toggle has a card's edge and inner padding, so its words never touch the edge high contrast draws. -->
<section class="space-y-4" aria-labelledby="{id}-toggle" data-settings-more={section}>
    <h3 class="text-xl font-semibold text-strong">
        <button
            id="{id}-toggle"
            type="button"
            class="card-base focus-ring flex min-h-11 w-full items-center justify-between gap-3 px-4 py-3 text-left md:px-6"
            aria-expanded={open}
            aria-controls="{id}-body"
            onclick={() => disclosure.toggle()}
        >
            <span class="min-w-0">
                <span class="block wrap-break-word">{$_('settings.more.title', { default: 'More options' })}</span>
                <span class="block max-w-prose font-sans text-sm font-normal text-muted wrap-break-word">{summary}</span>
            </span>
            <svg class="h-5 w-5 shrink-0 text-muted transition-transform motion-reduce:transition-none {open ? 'rotate-180' : ''}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 9 12 15 18 9" /></svg>
        </button>
    </h3>
    {#if open}
        <div id="{id}-body" class="space-y-8" data-settings-more-body>
            {@render children()}
        </div>
    {/if}
</section>
