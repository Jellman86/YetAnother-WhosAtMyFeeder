import { getContext, setContext } from 'svelte';

/**
 * Whether a component sits inside a card or panel. A state shown there is a line of text, not a
 * second box within the card (layout-patterns.md §6, "nothing boxed inside").
 */
const INSIDE_CARD = Symbol('inside-card');

export function markInsideCard(): void {
    setContext(INSIDE_CARD, true);
}

export function isInsideCard(): boolean {
    return getContext<boolean | undefined>(INSIDE_CARD) === true;
}
