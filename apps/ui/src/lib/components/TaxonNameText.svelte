<script lang="ts">
    import type { TaxonName } from '../taxonomy/nomenclature';

    /**
     * One taxon name with its italic runs set as `<i>`, the element HTML keeps for taxonomic
     * names: a genus or species is italic, a family or a common name is not.
     */
    interface Props {
        name: TaxonName;
        class?: string;
    }

    let { name, class: className = '' }: Props = $props();
</script>

<span class={className} data-taxon-name={name.kind}>{#each name.parts as part, index (index)}{#if part.italic}<i>{part.text}</i>{:else}{part.text}{/if}{/each}</span>
