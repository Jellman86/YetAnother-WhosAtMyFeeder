<script lang="ts">
    import { _ } from 'svelte-i18n';
    import type { HTMLButtonAttributes } from 'svelte/elements';

    /**
     * The one close button every dialog uses: a 44px round icon button with the same cross.
     * `surface` sits on a panel; `media` sits over a photograph or video, so it carries its own
     * dark fill to stay legible whatever the frame behind it shows.
     */
    interface Props extends Omit<HTMLButtonAttributes, 'type'> {
        tone?: 'surface' | 'media';
        label?: string;
        element?: HTMLButtonElement | null;
    }

    let { tone = 'surface', label, element = $bindable(null), class: className = '', ...rest }: Props = $props();

    const toneClass = $derived(tone === 'media' ? 'btn-on-dark bg-slate-950/60 hover:bg-slate-950/80' : 'btn-ghost');
</script>

<button
    bind:this={element}
    type="button"
    class="btn {toneClass} h-11 w-11 shrink-0 rounded-full p-0 {className}"
    aria-label={label ?? $_('common.close', { default: 'Close' })}
    data-dialog-close
    {...rest}
>
    <svg class="h-5 w-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true">
        <path d="M6 6l12 12M18 6 6 18" />
    </svg>
</button>
