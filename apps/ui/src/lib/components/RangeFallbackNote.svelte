<script lang="ts">
    import { _ } from 'svelte-i18n';
    import { fetchRangeDecision, type RangeDecisionDetail } from '../api/range-filter';

    let { eventId }: { eventId: string } = $props();

    let decision = $state.raw<RangeDecisionDetail | null>(null);

    // The decision lives on the server; read it once per record, and let a late answer for a
    // previous record fall away. Silence on failure: no note is the same as no change.
    $effect(() => {
        const requested = eventId;
        let current = true;
        decision = null;
        fetchRangeDecision(requested)
            .then((result) => {
                if (current) decision = result;
            })
            .catch(() => undefined);
        return () => {
            current = false;
        };
    });
</script>

{#if decision?.outcome === 'fallback'}
    <p class="mt-1" data-range-fallback-note>
        {$_('detection.range_fallback', {
            values: {
                original: decision.original_label,
                score: Math.round(decision.original_score * 100),
                region: decision.region_code
            },
            default: 'Range filter: the model first said {original} ({score}%), which eBird has never recorded in {region}, so its next answer in range was kept.'
        })}
    </p>
{/if}
