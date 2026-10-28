<script lang="ts">
    import ModelExecutionEvidence from './ModelExecutionEvidence.svelte';
    import { _ } from 'svelte-i18n';
    import type { GardenCapture } from '../api/garden';

    let { assessment, overridden = false, named = false, terminal = false }: { assessment: NonNullable<GardenCapture['automatic_check']>; overridden?: boolean; named?: boolean; terminal?: boolean } = $props();
</script>

<div class="space-y-1 text-sm" data-garden-automatic-check>
    <p class="text-3xs font-semibold uppercase tracking-[0.14em] {terminal ? 'text-slate-400' : 'text-slate-500 dark:text-slate-400'}">{$_('garden.automatic_check', { default: 'Automatic SpeciesNet check' })}</p>
    {#if overridden}
        <p>{$_('garden.automatic_overridden', { default: 'Your review overrides this automatic result. This capture will not be checked again automatically.' })}</p>
    {:else if assessment.decision_reason === 'below_threshold'}
        <p>{$_('garden.automatic_below_threshold', { default: 'Below the automatic animal threshold. Moved to Dismissed; restore the photo if you want to review it.' })}</p>
        {#if assessment.naming_score !== null && assessment.naming_score !== undefined && assessment.naming_threshold}
            <p>{$_('garden.automatic_score', { default: 'Species score {score}%; naming threshold {threshold}%.', values: { score: Math.round(assessment.naming_score * 100), threshold: Math.round(assessment.naming_threshold * 100) } })}</p>
        {/if}
    {:else if assessment.decision_reason === 'location_required'}
        <p>{$_('garden.automatic_location_required', { default: 'Animal detected. Set a country in Settings → Location so the model can name it automatically.' })}</p>
    {:else if assessment.decision_reason === 'identity_unavailable'}
        <p>{$_('garden.automatic_identity_unavailable', { default: 'Animal detected, but its name could not be bound to the local catalogue. No automatic name was saved.' })}</p>
    {:else if assessment.outcome === 'bird'}
        <p>{$_('garden.automatic_bird', { default: 'Bird suggested. Bird-only captures go to Dismissed; return this photo to review if the check is wrong.' })}</p>
    {:else if assessment.outcome === 'non_animal'}
        <p>{$_('garden.automatic_non_animal', { default: 'Blank scene or vehicle suggested. These captures go to Dismissed; return this photo to review if the check is wrong.' })}</p>
    {:else if assessment.outcome === 'animal' && named}
        <p>{$_('garden.automatic_named', { default: 'Confident animal. Confirmed and named automatically; dismiss the capture or discard the name if either is wrong.' })}</p>
    {:else if assessment.outcome === 'animal'}
        <p>{$_('garden.automatic_animal_manual', { default: 'Animal detected. Automatic naming is off or this older result awaits an updated automatic check.' })}</p>
    {:else if assessment.outcome === 'uncertain'}
        <p>{$_('garden.automatic_uncertain_pending', { default: 'This older uncertain result is waiting for the updated automatic check.' })}</p>
    {:else}
        <p>{$_('garden.automatic_unavailable', { default: 'The automatic check was unavailable. This photo stays in Needs review; checks retry after five minutes while Garden is enabled.' })}</p>
    {/if}
    <ModelExecutionEvidence {terminal} execution={assessment.execution ?? (assessment.variant && assessment.devices?.length ? {
        devices: assessment.devices, checked_at: `${assessment.checked_at}${assessment.checked_at.endsWith('Z') || assessment.checked_at.includes('+') ? '' : 'Z'}`
    } : null)} />
</div>
