<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { GardenCapture } from '../api/garden';

    let { assessment, overridden = false }: { assessment: NonNullable<GardenCapture['automatic_check']>; overridden?: boolean } = $props();
</script>

<div class="space-y-1 border-t border-line-soft pt-3 text-sm" data-garden-automatic-check>
    <p class="font-semibold">{$_('garden.automatic_check', { default: 'Automatic SpeciesNet check' })}</p>
    {#if overridden}
        <p>{$_('garden.automatic_overridden', { default: 'Your review overrides this automatic result. This capture will not be checked again automatically.' })}</p>
    {:else if assessment.outcome === 'bird'}
        <p>{$_('garden.automatic_bird', { default: 'Bird suggested. Bird-only captures go to Dismissed; return this photo to review if the check is wrong.' })}</p>
    {:else if assessment.outcome === 'non_animal'}
        <p>{$_('garden.automatic_non_animal', { default: 'Blank scene or vehicle suggested. These captures go to Dismissed; return this photo to review if the check is wrong.' })}</p>
    {:else if assessment.outcome === 'animal'}
        <p>{$_('garden.automatic_animal', { default: 'Non-bird animal suggested. Check the photo and confirm animal presence yourself.' })}</p>
    {:else if assessment.outcome === 'uncertain'}
        <p>{$_('garden.automatic_uncertain', { default: 'Uncertain result. This photo still needs your review.' })}</p>
    {:else}
        <p>{$_('garden.automatic_unavailable', { default: 'The automatic check was unavailable. This photo stays in Needs review; checks retry after five minutes while Garden is enabled.' })}</p>
    {/if}
</div>
