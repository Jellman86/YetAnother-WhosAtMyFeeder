<script lang="ts">
    import type { Snippet } from 'svelte';
    import { subheadingLevel } from './heading-level';

    interface Props {
        id?: string;
        /** `label` for a subheading that names one switch row, at the size of a row label. */
        size?: 'group' | 'label';
        /** Set by a subheading that holds further subheadings, which it then sends one level down. */
        level?: 3 | 4 | 5 | 6;
        children: Snippet;
    }

    let { id, size = 'group', level: given, children }: Props = $props();
    const inherited = subheadingLevel();
    const level = $derived(given ?? inherited);
</script>

<!-- A name for a few rows inside a card, in the reading face: the display face has no weight under
     semibold and is too dense at this size. Its level follows the card it sits in. -->
<svelte:element this={`h${level}`} {id} class="font-sans font-semibold text-strong {size === 'label' ? 'text-base' : 'text-sm'}" data-settings-subheading>
    {@render children()}
</svelte:element>
