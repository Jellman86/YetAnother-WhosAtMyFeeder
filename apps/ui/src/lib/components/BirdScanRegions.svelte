<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { BirdScanResponse } from '../api/media';
    import BirdCountRegionPreview from './BirdCountRegionPreview.svelte';

    let { response, imageUrl }: { response: BirdScanResponse; imageUrl: string | null } = $props();
    let open = $state(false);
    let shown = $state(8);
    const groups = $derived([
        { key: 'unconfirmed', regions: response.unconfirmed_regions ?? [], title: $_('detection.bird_scan.regions_unconfirmed', { default: 'Possible birds, not counted' }) },
        { key: 'excluded', regions: response.excluded_regions ?? [], title: $_('detection.bird_scan.regions_excluded', { default: 'Not a bird, not counted' }) }
    ]);
    const total = $derived(groups.reduce((sum, group) => sum + group.regions.length, 0));

    function reason(code: string): string {
        if (code === 'shares_counted_pixels') return $_('detection.bird_scan.region_shared', { default: 'Overlaps a confirmed bird, so it may be part of it' });
        if (code === 'individuality_unresolved') return $_('detection.bird_scan.region_individuality', { default: 'Could be separate birds or parts of one' });
        if (code === 'own_crop_nonbird') return $_('detection.bird_scan.region_nonbird', { default: 'Classified as not a bird' });
        if (code === 'confirmation_budget_exhausted') return $_('detection.bird_scan.region_budget', { default: 'Not checked within this scan’s limit' });
        return $_('detection.bird_scan.region_uncertain', { default: 'Not clear enough to count as a bird' });
    }
</script>

{#if total > 0}
    <details class="group w-full basis-full text-xs text-slate-600 dark:text-slate-300" ontoggle={(event) => { open = event.currentTarget.open; }} data-bird-scan-regions>
        <summary class="flex min-h-11 cursor-pointer items-center gap-2 rounded-lg focus-ring">
            <svg class="h-4 w-4 shrink-0 transition-transform group-open:rotate-90 motion-reduce:transition-none" viewBox="0 0 20 20" fill="currentColor" aria-hidden="true"><path d="m7 4 6 6-6 6V4Z" /></svg>
            {$_('detection.bird_scan.regions_summary', { values: { count: total }, default: '{count, plural, one {Show the area that was not counted} other {Show the # areas that were not counted}}' })}
        </summary>
        {#if open}
            {#each groups as group (group.key)}
                {#if group.regions.length > 0}
                    <p class="py-2 font-semibold">{group.title}</p>
                    <ol class="divide-y divide-slate-200 dark:divide-slate-700">
                        {#each group.regions.slice(0, shown) as region, index (`${group.key}-${region.candidate_id}-${index}`)}
                            {@const label = $_('detection.bird_scan.region_label', { values: { number: index + 1 }, default: 'Area {number}, not counted' })}
                            <li class="flex min-w-0 items-center gap-3 py-2" data-bird-scan-region={group.key}>
                                {#if imageUrl}<BirdCountRegionPreview src={imageUrl} box={region.box} {label} reason={reason(region.reason)} />{/if}
                                <div class="min-w-0"><p>{label}</p><p class="text-slate-500 dark:text-slate-400">{reason(region.reason)}</p></div>
                            </li>
                        {/each}
                    </ol>
                {/if}
            {/each}
            {#if groups.some((group) => group.regions.length > shown)}
                <button type="button" class="btn btn-ghost min-h-11" onclick={() => { shown += 8; }}>{$_('detection.bird_scan.regions_show_more', { default: 'Show more areas' })}</button>
            {/if}
        {/if}
    </details>
{/if}
