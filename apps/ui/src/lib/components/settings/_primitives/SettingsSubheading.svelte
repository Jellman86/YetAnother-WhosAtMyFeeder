<script lang="ts">
    import type { Snippet } from 'svelte';
    import { subheadingLevel } from './heading-level';

    interface Props {
        id?: string;
        /** `label` for a subheading that names one switch row, at the size of a row label. */
        size?: 'group' | 'label';
        children: Snippet;
    }

    let { id, size = 'group', children }: Props = $props();
    const level = subheadingLevel();
</script>

<!-- A name for a few rows inside a card, in the reading face: the display face has no weight under
     semibold and is too dense at this size. Its level follows the card it sits in. -->
<svelte:element this={`h${level}`} {id} class="font-sans font-semibold text-strong {size === 'label' ? 'text-base' : 'text-sm'}" data-settings-subheading>
    {@render children()}
</svelte:element>
