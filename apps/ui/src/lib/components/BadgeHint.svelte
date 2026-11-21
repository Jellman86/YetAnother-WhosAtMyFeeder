<script lang="ts">
    import type { Snippet } from 'svelte';
    import type { HTMLButtonAttributes } from 'svelte/elements';
    import { explanation } from '../utils/explanation';

    interface Props extends Omit<HTMLButtonAttributes, 'children' | 'class'> {
        /** What the badge means, shown on hover, focus or tap and read as its description. */
        text: string;
        /** A name for a badge with no words of its own (an icon). A badge with words is named by them. */
        label?: string;
        class?: string;
        /**
         * A badge set in a line of small text: give it a full 44px touch target without making the line
         * any taller, by padding the button out and pulling the margin back by the same amount.
         */
        target?: boolean;
        children: Snippet;
    }

    let { text, label, class: className = '', target = false, children, ...attributes }: Props = $props();
</script>

<button
    {...attributes}
    type="button"
    aria-label={label}
    class="pointer-events-auto focus-visible:outline-hidden focus-visible:ring-2 focus-visible:ring-focus {target ? 'inline-flex min-h-11 min-w-11 -my-3.5 items-center justify-center' : ''} {className}"
    use:explanation={{ text, toggle: true }}
    data-badge-hint
>
    {@render children()}
</button>
