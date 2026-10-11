<script lang="ts">
    import type { Snippet } from 'svelte';
    import type { HTMLButtonAttributes } from 'svelte/elements';
    import { explanation } from '../utils/explanation';

    interface Props extends Omit<HTMLButtonAttributes, 'children' | 'class'> {
        text: string;
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
    aria-label={label ?? text}
    class="pointer-events-auto focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand-500 {target ? 'inline-flex min-h-11 min-w-11 -my-3.5 items-center justify-center' : ''} {className}"
    use:explanation={{ text, toggle: true }}
    data-badge-hint
>
    {@render children()}
</button>
