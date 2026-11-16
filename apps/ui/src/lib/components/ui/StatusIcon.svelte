<script lang="ts">
    import type { Tone } from './tone';

    /**
     * A shape per tone, so a tone is told apart without its colour: a tick for ok, a diamond with a
     * bar for attention, a cross for fail, a filled disc for info and an open ring for neutral.
     * Decorative: the words beside it say the state.
     */
    let { tone, class: className = 'h-4 w-4' }: { tone: Tone; class?: string } = $props();
</script>

<svg class="shrink-0 {className}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" data-tone-icon={tone}>
    {#if tone === 'ok'}
        <circle cx="8" cy="8" r="6.25" />
        <path d="M5.25 8.25l1.9 1.9 3.6-4.15" />
    {:else if tone === 'attention'}
        <path d="M8 1.75L14.25 8 8 14.25 1.75 8z" />
        <path d="M8 5.25v3.25" />
        <path d="M8 10.75v.01" stroke-width="2.25" />
    {:else if tone === 'fail'}
        <circle cx="8" cy="8" r="6.25" />
        <path d="M5.75 5.75l4.5 4.5M10.25 5.75l-4.5 4.5" />
    {:else if tone === 'info'}
        <circle cx="8" cy="8" r="4.25" fill="currentColor" stroke="none" />
    {:else}
        <circle cx="8" cy="8" r="4.5" />
    {/if}
</svg>
